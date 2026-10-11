import os
import json
import asyncio
from threading import Thread

import discord
from discord import app_commands
from discord.ext import commands

# ----------------------------------------------------------------------------
# keep_alive embutido aqui dentro (sem depender de um arquivo separado),
# pra evitar erro de "módulo não encontrado" em hosts que só sobem um único
# arquivo. Sobe um mini servidor Flask só pra ter uma URL que responde, caso
# o host (ou um serviço tipo UptimeRobot) precise bater nela pra manter o
# processo acordado. Se o Flask não estiver instalado, não trava o bot.
# ----------------------------------------------------------------------------
def keep_alive():
    try:
        from flask import Flask
    except ImportError:
        print("Flask não instalado — pulando o keep_alive (o bot continua normalmente).")
        return

    app = Flask("keep_alive")

    @app.route("/")
    def home():
        return "O bot está online!"

    def run():
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)

    t = Thread(target=run)
    t.daemon = True
    t.start()


# ============================================================================
# TOKEN: no Pydroid3, pode colar direto na segunda linha abaixo. No Render
# (ou qualquer lugar que vá pro GitHub), configure a variável de ambiente
# DISCORD_TOKEN no painel do serviço — NUNCA deixe o token escrito aqui se
# for subir esse código pra um repositório.
# ============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
# ============================================================================

# ----------------------------------------------------------------------------
# Persistência simples em arquivos JSON (sem necessidade de banco de dados)
# ----------------------------------------------------------------------------

DATA_DIR = "data"
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
STOCK_FILE = os.path.join(DATA_DIR, "stock.json")
TICKETS_FILE = os.path.join(DATA_DIR, "tickets.json")
HELP_TICKETS_FILE = os.path.join(DATA_DIR, "help_tickets.json")
PANELS_FILE = os.path.join(DATA_DIR, "panels.json")
HELP_PANELS_FILE = os.path.join(DATA_DIR, "help_panels.json")
HELP_OPTIONS_FILE = os.path.join(DATA_DIR, "help_options.json")
SALES_FILE = os.path.join(DATA_DIR, "sales.json")


def load_json(path, default):
    if not os.path.exists(path):
        save_json(path, default)
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


config_data = load_json(CONFIG_FILE, {})
stock_data = load_json(STOCK_FILE, {})
tickets_data = load_json(TICKETS_FILE, {})
help_tickets_data = load_json(HELP_TICKETS_FILE, {})
panels_data = load_json(PANELS_FILE, {})
help_panels_data = load_json(HELP_PANELS_FILE, {})
help_options_data = load_json(HELP_OPTIONS_FILE, {})
sales_data = load_json(SALES_FILE, {})


def get_guild_config(guild_id: int) -> dict:
    gid = str(guild_id)
    defaults = {
        "pix": None,
        "cargo_dono_id": None,
        "cargo_administrador_id": None,
        "cargo_vendedor_id": None,
        "cargo_responsavel_id": None,
        "cargo_membro_id": None,
        "canal_logs_id": None,
        "canal_avaliacoes_id": None,
        "canal_entregas_id": None,
        "ticket_category_id": None,
        "ticket_ajuda_category_id": None,
    }
    if gid not in config_data:
        # migra o campo antigo "admin_role_id" (versões anteriores do bot), se existir
        config_data[gid] = dict(defaults)
        save_json(CONFIG_FILE, config_data)
    else:
        cfg = config_data[gid]
        changed = False
        if "cargo_vendedor_id" not in cfg and cfg.get("admin_role_id"):
            cfg["cargo_vendedor_id"] = cfg["admin_role_id"]
            changed = True
        for key, value in defaults.items():
            if key not in cfg:
                cfg[key] = value
                changed = True
        if changed:
            save_json(CONFIG_FILE, config_data)
    return config_data[gid]


def get_staff_roles(guild: discord.Guild, cfg: dict) -> list:
    """Cargos com acesso aos tickets de VENDAS: dono, administrador e vendedor."""
    roles = []
    for key in ("cargo_dono_id", "cargo_administrador_id", "cargo_vendedor_id"):
        rid = cfg.get(key)
        if rid:
            role = guild.get_role(rid)
            if role:
                roles.append(role)
    return roles


def get_help_staff_roles(guild: discord.Guild, cfg: dict) -> list:
    """Cargos com acesso aos tickets de AJUDA: dono, administrador e responsável por ticket."""
    roles = []
    for key in ("cargo_dono_id", "cargo_administrador_id", "cargo_responsavel_id"):
        rid = cfg.get(key)
        if rid:
            role = guild.get_role(rid)
            if role:
                roles.append(role)
    return roles


# IDs de usuário com acesso de dono garantido, não importa o que aconteça
# com cargos/permissões do servidor. Adicione mais IDs separados por vírgula.
OWNER_USER_IDS = {1530756434898194438}


def is_owner(interaction: discord.Interaction) -> bool:
    """Dono da loja: quem está em OWNER_USER_IDS, tem permissão real de
    Administrador no servidor, ou o cargo definido como 'Cargo dono' em
    /configurar. Tem acesso total (estoque, painel, configurações e saldo)."""
    if interaction.user.id in OWNER_USER_IDS:
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    cfg = get_guild_config(interaction.guild_id)
    dono_id = cfg.get("cargo_dono_id")
    return bool(dono_id and any(r.id == dono_id for r in interaction.user.roles))


def require_owner():
    """Decorator pra comandos que só o dono da loja pode usar."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")
    return app_commands.check(predicate)


async def send_log(guild_id: int, message: str = None, embed: discord.Embed = None):
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_logs_id")
    if not canal_id:
        return
    channel = bot.get_channel(canal_id)
    if channel:
        try:
            await channel.send(content=message, embed=embed)
        except discord.HTTPException:
            pass


async def send_delivery_log(guild_id: int, embed: discord.Embed):
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_entregas_id")
    if not canal_id:
        return
    channel = bot.get_channel(canal_id)
    if channel:
        try:
            await channel.send(embed=embed, content="🛒 Faça seu pedido também!")
        except discord.HTTPException:
            pass


async def send_review_public(guild_id: int, message: str):
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_avaliacoes_id")
    if not canal_id:
        return
    channel = bot.get_channel(canal_id)
    if channel:
        try:
            await channel.send(message)
        except discord.HTTPException:
            pass


def get_guild_stock(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in stock_data:
        stock_data[gid] = {}
        save_json(STOCK_FILE, stock_data)
    return stock_data[gid]


def get_guild_sales(guild_id: int) -> list:
    gid = str(guild_id)
    if gid not in sales_data:
        sales_data[gid] = []
        save_json(SALES_FILE, sales_data)
    return sales_data[gid]


def record_sale(guild_id: int, product_name: str, price: float, buyer_id: int, admin_id: int):
    sales = get_guild_sales(guild_id)
    sales.append({"produto": product_name, "preco": price, "comprador_id": buyer_id, "admin_id": admin_id})
    sales_data[str(guild_id)] = sales
    save_json(SALES_FILE, sales_data)


def get_guild_panels(guild_id: int) -> list:
    gid = str(guild_id)
    if gid not in panels_data:
        panels_data[gid] = []
        save_json(PANELS_FILE, panels_data)
    return panels_data[gid]


def add_panel_record(guild_id: int, channel_id: int, message_id: int, banner_url: str | None, titulo: str, descricao: str):
    panels = get_guild_panels(guild_id)
    panels.append(
        {
            "channel_id": channel_id,
            "message_id": message_id,
            "banner_url": banner_url,
            "titulo": titulo,
            "descricao": descricao,
        }
    )
    panels_data[str(guild_id)] = panels
    save_json(PANELS_FILE, panels_data)


async def refresh_panels(client: discord.Client, guild_id: int):
    """Atualiza o menu de produtos de todos os painéis já publicados nesse
    servidor, para refletir o estoque atual assim que ele muda."""
    gid = str(guild_id)
    panels = panels_data.get(gid, [])
    still_valid = []
    for p in panels:
        if "titulo" not in p or "descricao" not in p:
            continue  # painel de um formato antigo (de antes do banner/título serem salvos) — descarta
        channel = client.get_channel(p["channel_id"])
        if channel is None:
            continue
        try:
            message = await channel.fetch_message(p["message_id"])
            layout = build_sales_panel_layout(guild_id, p.get("banner_url"), p["titulo"], p["descricao"])
            await message.edit(view=layout)
            still_valid.append(p)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue
    panels_data[gid] = still_valid
    save_json(PANELS_FILE, panels_data)


def get_guild_help_options(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in help_options_data:
        help_options_data[gid] = {}
        save_json(HELP_OPTIONS_FILE, help_options_data)
    return help_options_data[gid]


def get_guild_help_panels(guild_id: int) -> list:
    gid = str(guild_id)
    if gid not in help_panels_data:
        help_panels_data[gid] = []
        save_json(HELP_PANELS_FILE, help_panels_data)
    return help_panels_data[gid]


def add_help_panel_record(
    guild_id: int, channel_id: int, message_id: int, banner_url: str | None, titulo: str, descricao: str
):
    panels = get_guild_help_panels(guild_id)
    panels.append(
        {
            "channel_id": channel_id,
            "message_id": message_id,
            "banner_url": banner_url,
            "titulo": titulo,
            "descricao": descricao,
        }
    )
    help_panels_data[str(guild_id)] = panels
    save_json(HELP_PANELS_FILE, help_panels_data)


async def refresh_help_panels(client: discord.Client, guild_id: int):
    """Atualiza o menu de tipos de atendimento de todos os painéis de ticket
    já publicados, assim que uma opção é adicionada/removida."""
    gid = str(guild_id)
    panels = help_panels_data.get(gid, [])
    still_valid = []
    for p in panels:
        if "titulo" not in p or "descricao" not in p:
            continue  # painel de um formato antigo — descarta
        channel = client.get_channel(p["channel_id"])
        if channel is None:
            continue
        try:
            message = await channel.fetch_message(p["message_id"])
            layout = build_help_panel_layout(guild_id, p.get("banner_url"), p["titulo"], p["descricao"])
            await message.edit(view=layout)
            still_valid.append(p)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue
    help_panels_data[gid] = still_valid
    save_json(HELP_PANELS_FILE, help_panels_data)


def slugify(nome: str) -> str:
    return nome.strip().lower().replace(" ", "_")


# ----------------------------------------------------------------------------
# Bot
# ----------------------------------------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# ----------------------------------------------------------------------------
# /configurar — painel de configuração da loja (PIX, cargos e canais)
# ----------------------------------------------------------------------------

class PixModal(discord.ui.Modal, title="Configurar chave PIX"):
    pix = discord.ui.TextInput(
        label="Chave PIX",
        placeholder="CPF, e-mail, telefone ou chave aleatória",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        cfg["pix"] = self.pix.value.strip()
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)
        await interaction.response.send_message("Chave PIX salva ✅", ephemeral=True)


class SingleRoleSelect(discord.ui.RoleSelect):
    def __init__(self, field: str, label: str):
        super().__init__(placeholder=f"Selecione: {label}")
        self.field = field
        self.field_label = label

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cfg = get_guild_config(interaction.guild_id)
        cfg[self.field] = role.id
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)
        await interaction.response.edit_message(content=f"{self.field_label} definido como {role.mention} ✅", view=None)


class SingleRoleSelectView(discord.ui.View):
    def __init__(self, field: str, label: str):
        super().__init__(timeout=60)
        self.add_item(SingleRoleSelect(field, label))


class SingleChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, field: str, label: str):
        super().__init__(placeholder=f"Selecione: {label}", channel_types=[discord.ChannelType.text])
        self.field = field
        self.field_label = label

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        cfg = get_guild_config(interaction.guild_id)
        cfg[self.field] = channel.id
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)
        await interaction.response.edit_message(
            content=f"{self.field_label} definido como {channel.mention} ✅", view=None
        )


class SingleChannelSelectView(discord.ui.View):
    def __init__(self, field: str, label: str):
        super().__init__(timeout=60)
        self.add_item(SingleChannelSelect(field, label))


def build_config_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    def role_str(rid):
        role = guild.get_role(rid) if rid else None
        return role.mention if role else "não definido"

    def chan_str(cid):
        ch = guild.get_channel(cid) if cid else None
        return ch.mention if ch else "não definido"

    embed = discord.Embed(title="⚙️ Configuração da loja", color=discord.Color.blurple())
    embed.add_field(name="Pix vendedor", value="configurado ✅" if cfg.get("pix") else "não configurado", inline=False)
    embed.add_field(name="Cargo dono (acesso a tudo)", value=role_str(cfg.get("cargo_dono_id")), inline=False)
    embed.add_field(
        name="Cargo administrador (vendas + ajuda)", value=role_str(cfg.get("cargo_administrador_id")), inline=False
    )
    embed.add_field(name="Cargo vendedor (só vendas)", value=role_str(cfg.get("cargo_vendedor_id")), inline=False)
    embed.add_field(
        name="Responsável por ticket (só ajuda)", value=role_str(cfg.get("cargo_responsavel_id")), inline=False
    )
    embed.add_field(name="Cargo membro", value=role_str(cfg.get("cargo_membro_id")), inline=False)
    embed.add_field(name="Canal de logs", value=chan_str(cfg.get("canal_logs_id")), inline=False)
    embed.add_field(name="Canal de avaliações", value=chan_str(cfg.get("canal_avaliacoes_id")), inline=False)
    embed.add_field(name="Canal de entregas", value=chan_str(cfg.get("canal_entregas_id")), inline=False)
    return embed


class ConfigPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="💰 Pix vendedor", style=discord.ButtonStyle.blurple, custom_id="cfg_pix", row=0)
    async def pix_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="👑 Cargo dono", style=discord.ButtonStyle.gray, custom_id="cfg_dono", row=0)
    async def dono_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleRoleSelectView("cargo_dono_id", "Cargo dono"), ephemeral=True
        )

    @discord.ui.button(label="🛡️ Cargo administrador", style=discord.ButtonStyle.gray, custom_id="cfg_admin", row=0)
    async def admin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleRoleSelectView("cargo_administrador_id", "Cargo administrador"), ephemeral=True
        )

    @discord.ui.button(label="🛒 Cargo vendedor", style=discord.ButtonStyle.gray, custom_id="cfg_vendedor", row=1)
    async def vendedor_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleRoleSelectView("cargo_vendedor_id", "Cargo vendedor"), ephemeral=True
        )

    @discord.ui.button(label="📞 Responsável por ticket", style=discord.ButtonStyle.gray, custom_id="cfg_responsavel", row=1)
    async def responsavel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleRoleSelectView("cargo_responsavel_id", "Responsável por ticket"), ephemeral=True
        )

    @discord.ui.button(label="👤 Cargo membro", style=discord.ButtonStyle.gray, custom_id="cfg_membro", row=1)
    async def membro_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleRoleSelectView("cargo_membro_id", "Cargo membro"), ephemeral=True
        )

    @discord.ui.button(label="📜 Canal de logs", style=discord.ButtonStyle.gray, custom_id="cfg_logs", row=2)
    async def logs_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleChannelSelectView("canal_logs_id", "Canal de logs"), ephemeral=True
        )

    @discord.ui.button(label="⭐ Canal de avaliações", style=discord.ButtonStyle.gray, custom_id="cfg_avaliacoes", row=2)
    async def avaliacoes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleChannelSelectView("canal_avaliacoes_id", "Canal de avaliações"), ephemeral=True
        )

    @discord.ui.button(label="📦 Canal de entregas", style=discord.ButtonStyle.gray, custom_id="cfg_entregas", row=3)
    async def entregas_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            view=SingleChannelSelectView("canal_entregas_id", "Canal de entregas"), ephemeral=True
        )


@bot.tree.command(name="configurar", description="Configura o PIX, cargos e canais da loja")
@app_commands.default_permissions(administrator=True)
@require_owner()
async def configurar(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    embed = build_config_embed(interaction.guild, cfg)
    await interaction.response.send_message(embed=embed, view=ConfigPanelView(), ephemeral=True)


@bot.tree.command(name="debugperm", description="[Diagnóstico] Mostra suas permissões e cargos vistos pelo bot")
async def debugperm(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    roles_str = "\n".join(f"- {r.name} (ID: {r.id})" for r in interaction.user.roles if r.name != "@everyone") or "nenhum cargo"
    embed = discord.Embed(title="🔍 Diagnóstico de permissões", color=discord.Color.orange())
    embed.add_field(
        name="Administrador (permissão real do Discord)",
        value="✅ Sim" if interaction.user.guild_permissions.administrator else "❌ Não",
        inline=False,
    )
    embed.add_field(name="Seus cargos", value=roles_str, inline=False)
    embed.add_field(name="Cargo dono configurado", value=str(cfg.get("cargo_dono_id")), inline=True)
    embed.add_field(name="Cargo administrador configurado", value=str(cfg.get("cargo_administrador_id")), inline=True)
    embed.add_field(
        name="Seu ID está na lista fixa de donos?",
        value=f"✅ Sim ({interaction.user.id})" if interaction.user.id in OWNER_USER_IDS else f"❌ Não ({interaction.user.id})",
        inline=False,
    )
    embed.add_field(name="is_owner() resultado", value="✅ Libera" if is_owner(interaction) else "❌ Bloqueia", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="saldo", description="Mostra o total vendido no servidor (só tickets concluídos)")
@app_commands.default_permissions(administrator=True)
@require_owner()
async def saldo(interaction: discord.Interaction):
    sales = get_guild_sales(interaction.guild_id)
    total = sum(s["preco"] for s in sales)
    embed = discord.Embed(title="💰 Saldo do servidor", color=discord.Color.green())
    embed.add_field(name="Total vendido", value=f"R$ {total:.2f}", inline=True)
    embed.add_field(name="Vendas concluídas", value=str(len(sales)), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ----------------------------------------------------------------------------
# /estoque — gerenciamento de produtos
# ----------------------------------------------------------------------------

class EstoqueGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="estoque",
            description="Gerencia o estoque de produtos",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode gerenciar o estoque.")

    @app_commands.command(name="adicionar", description="Adiciona um novo produto ao estoque")
    @app_commands.describe(
        nome="Nome do produto",
        preco="Preço em reais (ex: 19.90)",
        quantidade="Quantidade disponível em estoque",
        descricao="Descrição do produto",
    )
    async def adicionar(self, interaction: discord.Interaction, nome: str, preco: float, quantidade: int, descricao: str):
        stock = get_guild_stock(interaction.guild_id)
        pid = slugify(nome)
        if pid in stock:
            await interaction.response.send_message("Já existe um produto com esse nome. Use /estoque editar.", ephemeral=True)
            return
        stock[pid] = {"nome": nome, "preco": preco, "quantidade": quantidade, "descricao": descricao}
        save_json(STOCK_FILE, stock_data)
        await refresh_panels(interaction.client, interaction.guild_id)
        await interaction.response.send_message(f"Produto **{nome}** adicionado com sucesso ✅", ephemeral=True)

    @app_commands.command(name="remover", description="Remove um produto do estoque")
    @app_commands.describe(nome="Nome do produto")
    async def remover(self, interaction: discord.Interaction, nome: str):
        stock = get_guild_stock(interaction.guild_id)
        pid = slugify(nome)
        if pid not in stock:
            await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
            return
        del stock[pid]
        save_json(STOCK_FILE, stock_data)
        await refresh_panels(interaction.client, interaction.guild_id)
        await interaction.response.send_message(f"Produto **{nome}** removido ✅", ephemeral=True)

    @app_commands.command(name="editar", description="Edita um produto existente")
    @app_commands.describe(
        nome="Nome do produto",
        preco="Novo preço (opcional)",
        quantidade="Nova quantidade (opcional)",
        descricao="Nova descrição (opcional)",
    )
    async def editar(
        self,
        interaction: discord.Interaction,
        nome: str,
        preco: float = None,
        quantidade: int = None,
        descricao: str = None,
    ):
        stock = get_guild_stock(interaction.guild_id)
        pid = slugify(nome)
        if pid not in stock:
            await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
            return
        if preco is not None:
            stock[pid]["preco"] = preco
        if quantidade is not None:
            stock[pid]["quantidade"] = quantidade
        if descricao is not None:
            stock[pid]["descricao"] = descricao
        save_json(STOCK_FILE, stock_data)
        await refresh_panels(interaction.client, interaction.guild_id)
        await interaction.response.send_message(f"Produto **{nome}** atualizado ✅", ephemeral=True)

    @app_commands.command(name="listar", description="Lista todos os produtos cadastrados")
    async def listar(self, interaction: discord.Interaction):
        stock = get_guild_stock(interaction.guild_id)
        if not stock:
            await interaction.response.send_message("Nenhum produto cadastrado ainda.", ephemeral=True)
            return
        embed = discord.Embed(title="📦 Estoque atual", color=discord.Color.blurple())
        for p in stock.values():
            embed.add_field(
                name=p["nome"],
                value=f"Preço: R$ {p['preco']:.2f}\nEstoque: {p['quantidade']}\n{p['descricao']}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketOpcoesGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="ticket",
            description="Gerencia os tipos de atendimento do painel de ticket de ajuda",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode gerenciar os tipos de ticket.")

    @app_commands.command(name="adicionar", description="Adiciona um tipo de atendimento (ex: Suporte, Erro no pagamento)")
    @app_commands.describe(nome="Nome do tipo de atendimento", descricao="Descrição curta que aparece no menu (opcional)")
    async def adicionar(self, interaction: discord.Interaction, nome: str, descricao: str = ""):
        options = get_guild_help_options(interaction.guild_id)
        oid = slugify(nome)
        if oid in options:
            await interaction.response.send_message("Já existe um tipo com esse nome. Use /ticket remover primeiro.", ephemeral=True)
            return
        options[oid] = {"nome": nome, "descricao": descricao}
        help_options_data[str(interaction.guild_id)] = options
        save_json(HELP_OPTIONS_FILE, help_options_data)
        await refresh_help_panels(interaction.client, interaction.guild_id)
        await interaction.response.send_message(f"Tipo de atendimento **{nome}** adicionado ✅", ephemeral=True)

    @app_commands.command(name="remover", description="Remove um tipo de atendimento")
    @app_commands.describe(nome="Nome do tipo de atendimento")
    async def remover(self, interaction: discord.Interaction, nome: str):
        options = get_guild_help_options(interaction.guild_id)
        oid = slugify(nome)
        if oid not in options:
            await interaction.response.send_message("Tipo de atendimento não encontrado.", ephemeral=True)
            return
        del options[oid]
        help_options_data[str(interaction.guild_id)] = options
        save_json(HELP_OPTIONS_FILE, help_options_data)
        await refresh_help_panels(interaction.client, interaction.guild_id)
        await interaction.response.send_message(f"Tipo de atendimento **{nome}** removido ✅", ephemeral=True)

    @app_commands.command(name="listar", description="Lista todos os tipos de atendimento cadastrados")
    async def listar(self, interaction: discord.Interaction):
        options = get_guild_help_options(interaction.guild_id)
        if not options:
            await interaction.response.send_message("Nenhum tipo de atendimento cadastrado ainda.", ephemeral=True)
            return
        embed = discord.Embed(title="📞 Tipos de atendimento", color=discord.Color.blurple())
        for o in options.values():
            embed.add_field(name=o["nome"], value=o.get("descricao") or "—", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ----------------------------------------------------------------------------
# /painel — cria o painel de vendas com título, descrição e banner
# ----------------------------------------------------------------------------

class ProductSelect(discord.ui.Select):
    def __init__(self, guild_id: int):
        stock = get_guild_stock(guild_id)
        options = []
        for pid, p in stock.items():
            options.append(
                discord.SelectOption(
                    label=p["nome"][:100],
                    description=f"R$ {p['preco']:.2f} | Estoque: {p['quantidade']}"[:100],
                    value=pid,
                )
            )
        if not options:
            options = [discord.SelectOption(label="Sem produtos disponíveis", value="none")]
        super().__init__(
            placeholder="Selecione um produto...",
            options=options,
            custom_id="painel_product_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Nenhum produto disponível no momento.", ephemeral=True)
            return

        cfg = get_guild_config(interaction.guild_id)
        membro_role_id = cfg.get("cargo_membro_id")
        if membro_role_id and not any(r.id == membro_role_id for r in interaction.user.roles):
            role = interaction.guild.get_role(membro_role_id)
            nome_cargo = role.mention if role else "necessário"
            await interaction.response.send_message(
                f"Você precisa do cargo {nome_cargo} pra poder comprar aqui.", ephemeral=True
            )
            return

        await create_ticket(interaction, self.values[0])


class ProductSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(ProductSelect(guild_id))


def build_sales_panel_layout(guild_id: int, banner_url: str | None, titulo: str, descricao: str) -> discord.ui.LayoutView:
    """Monta o painel de vendas como um cartão único (Components V2):
    banner em cima, título/descrição, separador e o menu de produtos —
    tudo dentro da mesma borda colorida, sem parecer duas caixas separadas."""
    layout = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=discord.Color.gold())
    if banner_url:
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner_url)))
    container.add_item(discord.ui.TextDisplay(f"# {titulo}\n{descricao}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.ActionRow(ProductSelect(guild_id)))
    layout.add_item(container)
    return layout


class PanelModal(discord.ui.Modal, title="Criar Painel de Vendas"):
    titulo = discord.ui.TextInput(label="Título do painel", max_length=256)
    descricao = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        stock = get_guild_stock(interaction.guild_id)
        layout = build_sales_panel_layout(interaction.guild_id, self.banner_url, self.titulo.value, self.descricao.value)

        # Publica como mensagem normal do canal (não como resposta do comando),
        # assim não aparece "usou /painel" acima da mensagem.
        panel_message = await interaction.channel.send(view=layout)
        add_panel_record(
            interaction.guild_id, interaction.channel_id, panel_message.id,
            self.banner_url, self.titulo.value, self.descricao.value,
        )

        aviso = "" if stock else "\n\n⚠️ Nenhum produto cadastrado ainda — use /estoque adicionar (só você vê este aviso)."
        await interaction.response.send_message(f"Painel publicado ✅{aviso}", ephemeral=True)


class HelpTicketSelect(discord.ui.Select):
    def __init__(self, guild_id: int):
        options_dict = get_guild_help_options(guild_id)
        options = []
        for oid, o in options_dict.items():
            options.append(
                discord.SelectOption(label=o["nome"][:100], description=(o.get("descricao") or "")[:100], value=oid)
            )
        if not options:
            options = [discord.SelectOption(label="Sem tipos de atendimento cadastrados", value="none")]
        super().__init__(
            placeholder="Selecione o tipo de atendimento...",
            options=options,
            custom_id="help_ticket_type_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Nenhum tipo de atendimento disponível no momento.", ephemeral=True)
            return
        await create_help_ticket(interaction, self.values[0])


class HelpTicketSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(HelpTicketSelect(guild_id))


def build_help_panel_layout(guild_id: int, banner_url: str | None, titulo: str, descricao: str) -> discord.ui.LayoutView:
    """Mesma ideia do painel de vendas, só que pro painel de ticket de ajuda."""
    layout = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=discord.Color.blurple())
    if banner_url:
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner_url)))
    container.add_item(discord.ui.TextDisplay(f"# {titulo}\n{descricao}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.ActionRow(HelpTicketSelect(guild_id)))
    layout.add_item(container)
    return layout


class HelpPanelModal(discord.ui.Modal, title="Criar Painel de Ticket de Ajuda"):
    titulo = discord.ui.TextInput(label="Título do painel", max_length=256)
    descricao = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        options = get_guild_help_options(interaction.guild_id)
        layout = build_help_panel_layout(interaction.guild_id, self.banner_url, self.titulo.value, self.descricao.value)

        panel_message = await interaction.channel.send(view=layout)
        add_help_panel_record(
            interaction.guild_id, interaction.channel_id, panel_message.id,
            self.banner_url, self.titulo.value, self.descricao.value,
        )

        aviso = (
            ""
            if options
            else "\n\n⚠️ Nenhum tipo de atendimento cadastrado ainda — use /ticket adicionar (só você vê este aviso)."
        )
        await interaction.response.send_message(f"Painel de ticket de ajuda publicado ✅{aviso}", ephemeral=True)


class PainelGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="painel",
            description="Cria os painéis de vendas ou de ticket de ajuda",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")

    @app_commands.command(name="vendas", description="Cria o painel de vendas neste canal")
    @app_commands.describe(banner="Imagem de banner para o topo do painel (opcional)")
    async def vendas(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url if banner else None
        await interaction.response.send_modal(PanelModal(banner_url))

    @app_commands.command(name="ticket", description="Cria o painel de ticket de ajuda neste canal")
    @app_commands.describe(banner="Imagem de banner para o topo do painel (opcional)")
    async def ticket(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url if banner else None
        await interaction.response.send_modal(HelpPanelModal(banner_url))


# ----------------------------------------------------------------------------
# Sistema de tickets
# ----------------------------------------------------------------------------

TICKET_CATEGORY_NAME = "🛒 Ticket Vendas"
TICKET_AJUDA_CATEGORY_NAME = "📞 Ticket Ajuda"


async def get_or_create_ticket_category(guild: discord.Guild, cfg: dict) -> discord.CategoryChannel:
    # Usa uma categoria configurada manualmente em /configurar, se existir e for válida
    cat_id = cfg.get("ticket_category_id")
    if cat_id:
        existing = guild.get_channel(cat_id)
        if isinstance(existing, discord.CategoryChannel):
            return existing

    # Reaproveita a categoria padrão, se já tiver sido criada antes
    for cat in guild.categories:
        if cat.name == TICKET_CATEGORY_NAME:
            return cat

    staff_roles = get_staff_roles(guild, cfg)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True),
    }
    for role in staff_roles:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True)

    return await guild.create_category(TICKET_CATEGORY_NAME, overwrites=overwrites)


async def get_or_create_help_category(guild: discord.Guild, cfg: dict) -> discord.CategoryChannel:
    cat_id = cfg.get("ticket_ajuda_category_id")
    if cat_id:
        existing = guild.get_channel(cat_id)
        if isinstance(existing, discord.CategoryChannel):
            return existing

    for cat in guild.categories:
        if cat.name == TICKET_AJUDA_CATEGORY_NAME:
            return cat

    # Só dono, administrador e responsável por ticket enxergam essa categoria — vendedor NÃO tem acesso.
    staff_roles = get_help_staff_roles(guild, cfg)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True),
    }
    for role in staff_roles:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True)

    return await guild.create_category(TICKET_AJUDA_CATEGORY_NAME, overwrites=overwrites)


def get_ticket_owner_id(guild_id: int, channel_id: int) -> int | None:
    gid = str(guild_id)
    for uid, cid in tickets_data.get(gid, {}).items():
        if cid == channel_id:
            return int(uid)
    return None


def get_help_ticket_owner_id(guild_id: int, channel_id: int) -> int | None:
    gid = str(guild_id)
    for uid, cid in help_tickets_data.get(gid, {}).items():
        if cid == channel_id:
            return int(uid)
    return None


async def remove_help_ticket_record(guild_id: int, channel_id: int):
    gid = str(guild_id)
    user_tickets = help_tickets_data.get(gid, {})
    for uid, cid in list(user_tickets.items()):
        if cid == channel_id:
            del user_tickets[uid]
    help_tickets_data[gid] = user_tickets
    save_json(HELP_TICKETS_FILE, help_tickets_data)


async def create_help_ticket(interaction: discord.Interaction, option_id: str):
    guild = interaction.guild
    cfg = get_guild_config(guild.id)
    gid = str(guild.id)

    options = get_guild_help_options(guild.id)
    option = options.get(option_id)
    if not option:
        await interaction.response.send_message("Este tipo de atendimento não existe mais.", ephemeral=True)
        return

    user_tickets = help_tickets_data.get(gid, {})
    existing_channel_id = user_tickets.get(str(interaction.user.id))
    if existing_channel_id:
        existing_channel = guild.get_channel(existing_channel_id)
        if not existing_channel:
            try:
                existing_channel = await guild.fetch_channel(existing_channel_id)
            except (discord.NotFound, discord.Forbidden):
                existing_channel = None
        if existing_channel:
            await interaction.response.send_message(
                f"Você já tem um ticket de ajuda em aberto: <#{existing_channel_id}>", ephemeral=True
            )
            return
        else:
            del user_tickets[str(interaction.user.id)]
            help_tickets_data[gid] = user_tickets
            save_json(HELP_TICKETS_FILE, help_tickets_data)

    await interaction.response.send_message("Criando seu ticket de ajuda...", ephemeral=True)

    staff_roles = get_help_staff_roles(guild, cfg)
    category = await get_or_create_help_category(guild, cfg)
    if cfg.get("ticket_ajuda_category_id") != category.id:
        cfg["ticket_ajuda_category_id"] = category.id
        config_data[gid] = cfg
        save_json(CONFIG_FILE, config_data)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, manage_threads=True
        ),
    }
    for role in staff_roles:
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_threads=True
        )

    channel_name = f"ticket-ajuda-{interaction.user.name}".lower().replace(" ", "-")[:90]
    channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)

    user_tickets[str(interaction.user.id)] = channel.id
    help_tickets_data[gid] = user_tickets
    save_json(HELP_TICKETS_FILE, help_tickets_data)

    embed = discord.Embed(
        title=f"📞 Ticket de Ajuda — {option['nome']}",
        description=option.get("descricao") or "Descreva sua dúvida ou problema abaixo. Em breve alguém vai te atender.",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Aberto por: {interaction.user}")

    mention = interaction.user.mention + " " + " ".join(r.mention for r in staff_roles)
    await channel.send(content=mention, embed=embed, view=HelpTicketView())
    await channel.send("⏳ Aguarde, um administrador irá hospedar seu ticket em breve.")

    await send_log(
        guild.id, message=f"📞 Ticket de ajuda aberto: {channel.mention} — {interaction.user.mention}."
    )


async def create_ticket(interaction: discord.Interaction, product_id: str):
    guild = interaction.guild
    stock = get_guild_stock(guild.id)
    cfg = get_guild_config(guild.id)

    if product_id not in stock:
        await interaction.response.send_message("Este produto não existe mais.", ephemeral=True)
        return

    product = stock[product_id]
    if product["quantidade"] <= 0:
        await interaction.response.send_message("Produto esgotado no momento.", ephemeral=True)
        return

    gid = str(guild.id)
    user_tickets = tickets_data.get(gid, {})
    existing_channel_id = user_tickets.get(str(interaction.user.id))
    if existing_channel_id:
        existing_channel = guild.get_channel(existing_channel_id)
        if not existing_channel:
            try:
                existing_channel = await guild.fetch_channel(existing_channel_id)
            except (discord.NotFound, discord.Forbidden):
                existing_channel = None
        if existing_channel:
            await interaction.response.send_message(
                f"Você já tem um ticket em aberto: <#{existing_channel_id}>", ephemeral=True
            )
            return
        else:
            # o canal antigo não existe mais (foi apagado) — limpa o registro travado
            del user_tickets[str(interaction.user.id)]
            tickets_data[gid] = user_tickets
            save_json(TICKETS_FILE, tickets_data)

    await interaction.response.send_message("Criando seu ticket...", ephemeral=True)

    staff_roles = get_staff_roles(guild, cfg)
    category = await get_or_create_ticket_category(guild, cfg)
    if cfg.get("ticket_category_id") != category.id:
        cfg["ticket_category_id"] = category.id
        config_data[gid] = cfg
        save_json(CONFIG_FILE, config_data)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, manage_threads=True
        ),
    }
    for role in staff_roles:
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_threads=True
        )

    channel_name = f"ticket-{interaction.user.name}".lower().replace(" ", "-")[:90]
    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        topic=product_id,  # guarda o produto no tópico do canal (usado pelos botões)
    )

    user_tickets[str(interaction.user.id)] = channel.id
    tickets_data[gid] = user_tickets
    save_json(TICKETS_FILE, tickets_data)

    embed = discord.Embed(title=f"🛒 Pedido: {product['nome']}", color=discord.Color.green())
    embed.add_field(name="Preço", value=f"R$ {product['preco']:.2f}", inline=True)
    embed.add_field(name="Descrição", value=product["descricao"], inline=False)
    embed.set_footer(text=f"Comprador: {interaction.user}")

    mention = interaction.user.mention + " " + " ".join(r.mention for r in staff_roles)
    await channel.send(content=mention, embed=embed, view=TicketView())
    await channel.send("⏳ Aguarde, um vendedor irá hospedar seu ticket em breve.")

    await send_log(
        guild.id,
        f"🎫 Ticket aberto: {channel.mention} — comprador {interaction.user.mention}, produto **{product['nome']}**.",
    )

    # Thread privada — só quem já enxerga o canal E tem "Gerenciar tópicos"
    # (os cargos de dono/vendedor) consegue ver essa thread automaticamente.
    if staff_roles:
        try:
            thread = await channel.create_thread(
                name="🔒 Painel Admin",
                type=discord.ChannelType.private_thread,
                invitable=False,
            )
            await thread.send(
                f"Ticket de {interaction.user.mention} — clique abaixo para hospedar este atendimento.",
                view=HostView(),
            )
        except discord.HTTPException:
            pass  # servidor sem boost suficiente para threads privadas, por exemplo


async def remove_ticket_record(guild_id: int, channel_id: int):
    gid = str(guild_id)
    user_tickets = tickets_data.get(gid, {})
    for uid, cid in list(user_tickets.items()):
        if cid == channel_id:
            del user_tickets[uid]
    tickets_data[gid] = user_tickets
    save_json(TICKETS_FILE, tickets_data)


def is_admin(interaction: discord.Interaction) -> bool:
    """Acesso aos tickets de VENDAS: administrador real do Discord, dono, administrador da loja ou vendedor."""
    cfg = get_guild_config(interaction.guild_id)
    if interaction.user.guild_permissions.administrator:
        return True
    staff_ids = {cfg.get("cargo_dono_id"), cfg.get("cargo_administrador_id"), cfg.get("cargo_vendedor_id")}
    staff_ids.discard(None)
    return any(r.id in staff_ids for r in interaction.user.roles)


def is_help_staff(interaction: discord.Interaction) -> bool:
    """Acesso aos tickets de AJUDA: administrador real do Discord, dono, administrador da loja ou responsável por ticket.
    O cargo vendedor NÃO tem acesso aqui."""
    cfg = get_guild_config(interaction.guild_id)
    if interaction.user.guild_permissions.administrator:
        return True
    staff_ids = {cfg.get("cargo_dono_id"), cfg.get("cargo_administrador_id"), cfg.get("cargo_responsavel_id")}
    staff_ids.discard(None)
    return any(r.id in staff_ids for r in interaction.user.roles)


async def send_rating_request(guild_id: int, buyer_id: int, admin_id: int | None, label: str, context: str = "venda"):
    try:
        buyer = await bot.fetch_user(buyer_id)
        if context == "suporte":
            desc = "Como foi o atendimento do nosso suporte? Toque numa estrela abaixo."
        else:
            desc = f"Como foi sua experiência comprando **{label}**? Toque numa estrela abaixo."
        embed = discord.Embed(title="⭐ Avalie seu atendimento!", description=desc, color=discord.Color.gold())
        await buyer.send(embed=embed, view=RatingView(guild_id, admin_id, label, context))
    except discord.Forbidden:
        pass  # o comprador tem DMs fechadas pra membros do servidor


class RatingButton(discord.ui.Button):
    def __init__(self, stars: int):
        super().__init__(label="⭐" * stars, style=discord.ButtonStyle.gray, custom_id=f"rating_btn_{stars}")
        self.stars = stars

    async def callback(self, interaction: discord.Interaction):
        view: RatingView = self.view
        for child in view.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"Obrigado por avaliar com {'⭐' * self.stars}! Sua opinião é muito importante. 🙏",
            embed=None,
            view=view,
        )
        plural = "s" if self.stars != 1 else ""
        if view.context == "suporte":
            admin_msg = (
                f"🌟 Você acabou de receber **{self.stars} estrela{plural}** de um cliente "
                f"pelo atendimento de suporte que você prestou!"
            )
            public_msg = f"{'⭐' * self.stars} Nova avaliação recebida pelo atendimento de suporte!"
        else:
            admin_msg = (
                f"🌟 Você acabou de receber **{self.stars} estrela{plural}** de um cliente "
                f"pela venda de **{view.label}**!"
            )
            public_msg = f"{'⭐' * self.stars} Nova avaliação recebida pela venda de **{view.label}**!"

        if view.admin_id:
            try:
                admin = await bot.fetch_user(view.admin_id)
                await admin.send(admin_msg)
            except discord.Forbidden:
                pass
        await send_review_public(view.guild_id, public_msg)


class RatingView(discord.ui.View):
    def __init__(self, guild_id: int, admin_id: int | None, label: str, context: str = "venda"):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.admin_id = admin_id
        self.label = label
        self.context = context
        for i in range(1, 6):
            self.add_item(RatingButton(i))


class HelpTicketView(discord.ui.View):
    """Botões diretos no canal do ticket de ajuda: Hospedar e Fechar.
    Guarda quem hospedou no tópico do canal, pra saber quem notificar na avaliação."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Hospedar Ticket", style=discord.ButtonStyle.blurple, custom_id="help_ticket_hospedar")
    async def hospedar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_help_staff(interaction):
            await interaction.response.send_message(
                "Apenas a equipe de suporte pode hospedar tickets de ajuda.", ephemeral=True
            )
            return

        button.disabled = True
        button.label = f"Hospedado por {interaction.user.display_name}"
        await interaction.response.edit_message(view=self)

        try:
            await interaction.channel.edit(topic=str(interaction.user.id))
        except discord.HTTPException:
            pass

        await interaction.channel.send(
            f"🔔 O administrador {interaction.user.mention} hospedou seu ticket! Você será atendido em breve."
        )

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.red, custom_id="help_ticket_fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        buyer_id = get_help_ticket_owner_id(interaction.guild_id, interaction.channel_id)
        host_id_raw = interaction.channel.topic
        host_id = int(host_id_raw) if host_id_raw and host_id_raw.isdigit() else None

        await interaction.response.send_message("Fechando o ticket em instantes...", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete()
        finally:
            await remove_help_ticket_record(interaction.guild_id, interaction.channel_id)
            await send_log(
                interaction.guild_id, message=f"🔒 Ticket de ajuda fechado por {interaction.user.mention}."
            )
            if buyer_id:
                await send_rating_request(interaction.guild_id, buyer_id, host_id, "suporte", context="suporte")


class HostView(discord.ui.View):
    """Botão que fica na thread privada (só admins veem) para assumir o ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Hospedar Ticket", style=discord.ButtonStyle.blurple, custom_id="ticket_hospedar")
    async def hospedar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction):
            await interaction.response.send_message("Apenas a administração pode hospedar tickets.", ephemeral=True)
            return

        button.disabled = True
        button.label = f"Hospedado por {interaction.user.display_name}"
        await interaction.response.edit_message(view=self)

        # A thread é filha do canal do ticket — pegamos o canal pai pra avisar o comprador lá
        parent = interaction.channel.parent
        owner_id = get_ticket_owner_id(interaction.guild_id, parent.id) if parent else None
        if parent:
            aviso = f"🔔 O administrador {interaction.user.mention} hospedou seu ticket"
            if owner_id:
                aviso = f"🔔 {f'<@{owner_id}>'}, " + aviso[2:]
            await parent.send(aviso + "! Você será atendido em breve.")


class TicketView(discord.ui.View):
    """View sem estado próprio: lê o produto do tópico do canal, por isso pode
    ser registrada como persistente (funciona mesmo após reiniciar o bot)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.red, custom_id="ticket_fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Fechando o ticket em instantes...", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete()
        finally:
            await remove_ticket_record(interaction.guild_id, interaction.channel_id)
            await send_log(
                interaction.guild_id,
                message=f"🔒 Ticket fechado por {interaction.user.mention} (sem conclusão de pagamento).",
            )

    @discord.ui.button(label="Concluir Pagamento", style=discord.ButtonStyle.green, custom_id="ticket_concluir")
    async def concluir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "Apenas a administração pode concluir o pagamento.", ephemeral=True
            )
            return

        product_id = interaction.channel.topic
        stock = get_guild_stock(interaction.guild_id)
        product = stock.get(product_id)
        buyer_id = get_ticket_owner_id(interaction.guild_id, interaction.channel_id)

        if product and product["quantidade"] > 0:
            product["quantidade"] -= 1
            save_json(STOCK_FILE, stock_data)
            await refresh_panels(interaction.client, interaction.guild_id)

        if product and buyer_id:
            record_sale(interaction.guild_id, product["nome"], product["preco"], buyer_id, interaction.user.id)

            await send_log(
                interaction.guild_id,
                message=(
                    f"✅ Venda concluída: **{product['nome']}** (R$ {product['preco']:.2f}) — "
                    f"comprador <@{buyer_id}>, atendido por {interaction.user.mention}."
                ),
            )

            entrega_embed = discord.Embed(title=f"📦 {product['nome']}", color=discord.Color.green())
            entrega_embed.add_field(name="Preço", value=f"R$ {product['preco']:.2f}", inline=True)
            entrega_embed.add_field(name="Descrição", value=product["descricao"], inline=False)
            entrega_embed.set_footer(text=f"Comprador: <@{buyer_id}> | Atendido por: {interaction.user}")
            await send_delivery_log(interaction.guild_id, entrega_embed)

        await interaction.response.send_message(
            "✅ Pagamento concluído! Este ticket será fechado em alguns segundos..."
        )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        finally:
            await remove_ticket_record(interaction.guild_id, interaction.channel_id)
            if product and buyer_id:
                await send_rating_request(interaction.guild_id, buyer_id, interaction.user.id, product["nome"])

    @discord.ui.button(label="📋 Copiar PIX", style=discord.ButtonStyle.gray, custom_id="ticket_copiar_pix")
    async def copiar_pix(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild_id)
        pix = cfg.get("pix")
        if not pix:
            await interaction.response.send_message("Nenhuma chave PIX configurada ainda.", ephemeral=True)
            return
        # Discord não permite um bot copiar direto pra área de transferência do usuário;
        # mandando em bloco de código, é só manter o dedo pressionado sobre o texto pra copiar.
        await interaction.response.send_message(f"Chave PIX:\n```{pix}```", ephemeral=True)


# ----------------------------------------------------------------------------
# Registro de comandos e tratamento de erros
# ----------------------------------------------------------------------------

bot.tree.add_command(EstoqueGroup())
bot.tree.add_command(PainelGroup())
bot.tree.add_command(TicketOpcoesGroup())


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "Você precisa ser administrador para usar este comando."
    elif isinstance(error, app_commands.CheckFailure):
        msg = str(error) or "Você não tem permissão para usar este comando."
    else:
        msg = f"Ocorreu um erro: {error}"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


@bot.event
async def on_ready():
    # Registra as views persistentes para os botões/menus continuarem
    # funcionando em mensagens antigas após reiniciar o bot.
    bot.add_view(TicketView())
    bot.add_view(HostView())
    bot.add_view(HelpTicketView())
    for gid, panels in panels_data.items():
        for p in panels:
            if "titulo" not in p or "descricao" not in p:
                continue  # painel de um formato antigo — ignora, não trava o bot
            layout = build_sales_panel_layout(int(gid), p.get("banner_url"), p["titulo"], p["descricao"])
            bot.add_view(layout, message_id=p["message_id"])
    for gid, panels in help_panels_data.items():
        for p in panels:
            if "titulo" not in p or "descricao" not in p:
                continue
            layout = build_help_panel_layout(int(gid), p.get("banner_url"), p["titulo"], p["descricao"])
            bot.add_view(layout, message_id=p["message_id"])
    await bot.tree.sync()
    print(f"Bot conectado como {bot.user} (ID: {bot.user.id})")


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "COLOQUE_SEU_TOKEN_AQUI":
        raise SystemExit(
            "Defina seu token: no Pydroid3, cole na linha DISCORD_TOKEN no topo do arquivo; "
            "no Render, configure a variável de ambiente DISCORD_TOKEN no painel."
        )
    keep_alive()  # sobe o mini servidor web (só necessário no Render/hospedagem web)
    bot.run(DISCORD_TOKEN)
