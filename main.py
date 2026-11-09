import os
import re
import json
import time
import random
import asyncio
from datetime import datetime, timezone
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
TICKET_INFO_FILE = os.path.join(DATA_DIR, "ticket_info.json")
HELP_TICKETS_FILE = os.path.join(DATA_DIR, "help_tickets.json")
PANELS_FILE = os.path.join(DATA_DIR, "panels.json")
HELP_PANELS_FILE = os.path.join(DATA_DIR, "help_panels.json")
HELP_OPTIONS_FILE = os.path.join(DATA_DIR, "help_options.json")
SALES_FILE = os.path.join(DATA_DIR, "sales.json")
KEYS_FILE = os.path.join(DATA_DIR, "keys.json")
GIVEAWAYS_FILE = os.path.join(DATA_DIR, "giveaways.json")
COUPONS_FILE = os.path.join(DATA_DIR, "coupons.json")

FREE_STOCK_LIMIT = 10  # quantos produtos o plano grátis permite cadastrar (premium = ilimitado)


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
# produto/comprador de cada ticket de vendas: {guild: {canal_id: {"produto": pid, "comprador": user_id}}}
ticket_info_data = load_json(TICKET_INFO_FILE, {})
help_tickets_data = load_json(HELP_TICKETS_FILE, {})
panels_data = load_json(PANELS_FILE, {})
help_panels_data = load_json(HELP_PANELS_FILE, {})
help_options_data = load_json(HELP_OPTIONS_FILE, {})
sales_data = load_json(SALES_FILE, {})
# sorteios: {guild: {id_da_mensagem: {...}}}
giveaways_data = load_json(GIVEAWAYS_FILE, {})
# cupons de desconto: {guild: {NOME: {"desconto": %, "limite": n, "usos": [user_ids], "expira_em": ts, "criado_por": id}}}
coupons_data = load_json(COUPONS_FILE, {})
keys_data = load_json(KEYS_FILE, {})  # global (não é por servidor): {key: {"used": bool, "guild_id": int|None}}


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
        "premium": False,
        "cor_embed": None,
        "canal_boasvindas_id": None,
        "boasvindas_titulo": None,
        "boasvindas_texto": None,
        "boasvindas_banner_url": None,
        "sorteio_entradas": {},  # {id_do_cargo: quantas entradas ele vale nos sorteios}
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


def require_premium():
    """Decorator pra comandos que só funcionam com uma key premium resgatada
    (e só pro dono da loja usar, igual require_owner)."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in OWNER_USER_IDS:
            return True  # você (desenvolvedor do bot) sempre tem acesso, pra testar
        if not is_owner(interaction):
            raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")
        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("premium"):
            raise app_commands.CheckFailure(
                "🔒 Este é um recurso premium. Resgate uma key em /configurar para desbloquear."
            )
        return True
    return app_commands.check(predicate)


def generate_key() -> str:
    import secrets
    raw = secrets.token_hex(8).upper()  # 16 caracteres hex
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


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


async def _fetch_panel_message(client: discord.Client, p: dict):
    """Busca a mensagem de um painel. Retorna (mensagem, descartar).
    descartar=True só quando o canal/mensagem foram realmente apagados;
    erro passageiro (rede, rate limit) NÃO descarta o registro."""
    channel = client.get_channel(p["channel_id"])
    if channel is None:
        try:
            channel = await client.fetch_channel(p["channel_id"])
        except discord.NotFound:
            return None, True
        except discord.HTTPException:
            return None, False
    try:
        return await channel.fetch_message(p["message_id"]), False
    except discord.NotFound:
        return None, True
    except discord.HTTPException:
        return None, False


async def refresh_panels(client: discord.Client, guild_id: int):
    """Atualiza o menu de produtos de cada painel de vendas, mostrando só os
    produtos DAQUELE painel e o estoque atual. Também zera o ✓ da última escolha."""
    gid = str(guild_id)
    still_valid = []
    for p in panels_data.get(gid, []):
        message, descartar = await _fetch_panel_message(client, p)
        if descartar:
            continue
        if message is not None:
            try:
                # Só troca o menu — o embed (banner/título/descrição) fica igual.
                await message.edit(view=ProductSelectView(guild_id, str(p["message_id"])))
            except discord.NotFound:
                continue
            except discord.HTTPException:
                pass
        still_valid.append(p)
    panels_data[gid] = still_valid
    save_json(PANELS_FILE, panels_data)


def list_sales_panels(guild_id: int) -> list:
    return list(panels_data.get(str(guild_id), []))


def panel_label(guild: discord.Guild | None, p: dict) -> str:
    canal = guild.get_channel(p["channel_id"]) if guild else None
    nome_canal = f"#{canal.name}" if canal else "canal apagado"
    titulo = p.get("titulo") or f"Painel {p['message_id']}"
    return f"{nome_canal} — {titulo}"[:100]


def resolve_panel_id(guild_id: int, painel: str | None) -> tuple[str | None, str | None]:
    """Descobre em qual painel o comando de estoque deve mexer. Retorna (painel_id, erro)."""
    panels = list_sales_panels(guild_id)
    ids = {str(p["message_id"]) for p in panels}
    if painel:
        if painel in ids:
            return painel, None
        return None, "Painel não encontrado — escolha um da lista que aparece no campo **painel**."
    if not panels:
        return None, "Você ainda não tem nenhum painel de vendas. Crie um com /painel vendas primeiro."
    if len(panels) == 1:
        return str(panels[0]["message_id"]), None
    return None, "Você tem mais de um painel de vendas — escolha qual no campo **painel**."


def find_product(stock: dict, panel_id: str, nome: str):
    alvo = slugify(nome)
    for pid, p in stock.items():
        if p.get("painel_id") == panel_id and slugify(p["nome"]) == alvo:
            return pid, p
    return None, None


def migrate_legacy_products():
    """Produtos criados antes dos painéis terem estoque próprio não têm 'painel_id'.
    Eles passam a pertencer ao primeiro painel do servidor (os novos painéis começam vazios)."""
    changed = False
    for gid, stock in stock_data.items():
        panels = panels_data.get(gid, [])
        if not panels:
            continue
        padrao = str(panels[0]["message_id"])
        for p in stock.values():
            if "painel_id" not in p:
                p["painel_id"] = padrao
                changed = True
    if changed:
        save_json(STOCK_FILE, stock_data)


async def painel_autocomplete(interaction: discord.Interaction, current: str) -> list:
    out = []
    for p in list_sales_panels(interaction.guild_id):
        label = panel_label(interaction.guild, p)
        if current.lower() in label.lower():
            out.append(app_commands.Choice(name=label, value=str(p["message_id"])))
    return out[:25]


async def produto_autocomplete(interaction: discord.Interaction, current: str) -> list:
    painel = getattr(interaction.namespace, "painel", None)
    panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
    if erro:
        return []
    out = []
    for p in get_guild_stock(interaction.guild_id).values():
        if p.get("painel_id") == panel_id and current.lower() in p["nome"].lower():
            out.append(app_commands.Choice(name=p["nome"][:100], value=p["nome"][:100]))
    return out[:25]


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
    já publicados (e zera o ✓ da última escolha)."""
    gid = str(guild_id)
    still_valid = []
    for p in help_panels_data.get(gid, []):
        message, descartar = await _fetch_panel_message(client, p)
        if descartar:
            continue
        if message is not None:
            try:
                await message.edit(view=HelpTicketSelectView(guild_id))
            except discord.NotFound:
                continue
            except discord.HTTPException:
                pass
        still_valid.append(p)
    help_panels_data[gid] = still_valid
    save_json(HELP_PANELS_FILE, help_panels_data)


def slugify(nome: str) -> str:
    return nome.strip().lower().replace(" ", "_")


# ----------------------------------------------------------------------------
# Bot
# ----------------------------------------------------------------------------

intents = discord.Intents.default()
intents.members = True  # necessário pro evento de boas-vindas (recurso premium)
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

    premium = cfg.get("premium", False)
    embed.add_field(
        name="Key",
        value="✅ ativa — recursos premium liberados" if premium else "nenhuma (recursos de nome/foto/cor bloqueados)",
        inline=False,
    )
    if premium:
        embed.add_field(name="Canal de boas-vindas", value=chan_str(cfg.get("canal_boasvindas_id")), inline=False)
    else:
        embed.add_field(
            name="Limite do estoque (plano grátis)", value=f"{FREE_STOCK_LIMIT} produtos", inline=False
        )
    return embed


class KeyModal(discord.ui.Modal, title="Resgatar Key Premium"):
    key = discord.ui.TextInput(label="Key", placeholder="XXXX-XXXX-XXXX-XXXX", max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        k = self.key.value.strip().upper()
        info = keys_data.get(k)
        if not info:
            await interaction.response.send_message("❌ Key inválida.", ephemeral=True)
            return
        if info.get("used"):
            await interaction.response.send_message("❌ Essa key já foi usada em outro servidor.", ephemeral=True)
            return

        info["used"] = True
        info["guild_id"] = interaction.guild_id
        keys_data[k] = info
        save_json(KEYS_FILE, keys_data)

        cfg = get_guild_config(interaction.guild_id)
        cfg["premium"] = True
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)

        await interaction.response.send_message(
            "✅ Key resgatada! Recursos premium liberados pra este servidor — confira com /personalizar.",
            ephemeral=True,
        )


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

    @discord.ui.button(label="🔑 Resgatar key", style=discord.ButtonStyle.green, custom_id="cfg_key", row=3)
    async def key_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(KeyModal())

    @discord.ui.button(label="👋 Canal de boas-vindas", style=discord.ButtonStyle.gray, custom_id="cfg_boasvindas", row=4)
    async def boasvindas_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("premium") and interaction.user.id not in OWNER_USER_IDS:
            await interaction.response.send_message(
                "🔒 Recurso premium — resgate uma key primeiro (botão 🔑 acima).", ephemeral=True
            )
            return
        await interaction.response.send_message(
            view=SingleChannelSelectView("canal_boasvindas_id", "Canal de boas-vindas"), ephemeral=True
        )


@bot.tree.command(name="configurar", description="Configura o PIX, cargos e canais da loja")
@app_commands.default_permissions(administrator=True)
@require_owner()
async def configurar(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    embed = build_config_embed(interaction.guild, cfg)
    await interaction.response.send_message(embed=embed, view=ConfigPanelView(), ephemeral=True)


@bot.tree.command(name="gerarkey", description="[Só o dono do bot] Gera uma nova key premium pra vender")
async def gerarkey(interaction: discord.Interaction):
    if interaction.user.id not in OWNER_USER_IDS:
        await interaction.response.send_message("Só o dono do bot pode gerar keys.", ephemeral=True)
        return
    key = generate_key()
    while key in keys_data:
        key = generate_key()
    keys_data[key] = {"used": False, "guild_id": None}
    save_json(KEYS_FILE, keys_data)
    await interaction.response.send_message(f"🔑 Nova key gerada:\n```{key}```", ephemeral=True)


@bot.tree.command(name="listarkeys", description="[Só o dono do bot] Lista as keys geradas e o status delas")
async def listarkeys(interaction: discord.Interaction):
    if interaction.user.id not in OWNER_USER_IDS:
        await interaction.response.send_message("Só o dono do bot pode ver isso.", ephemeral=True)
        return
    if not keys_data:
        await interaction.response.send_message("Nenhuma key gerada ainda.", ephemeral=True)
        return
    nao_usadas = [k for k, v in keys_data.items() if not v.get("used")]
    usadas = [(k, v.get("guild_id")) for k, v in keys_data.items() if v.get("used")]
    embed = discord.Embed(title="🔑 Keys geradas", color=discord.Color.gold())
    embed.add_field(
        name=f"Disponíveis ({len(nao_usadas)})", value="\n".join(f"`{k}`" for k in nao_usadas[:15]) or "nenhuma",
        inline=False,
    )
    embed.add_field(
        name=f"Já usadas ({len(usadas)})",
        value="\n".join(f"`{k}` — servidor {gid}" for k, gid in usadas[:15]) or "nenhuma",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


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

class ResetEstoqueView(discord.ui.View):
    """Confirmação do /estoque resetar — apagar produtos não dá pra desfazer."""

    def __init__(self, user_id: int, guild_id: int, panel_id: str | None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id
        self.panel_id = panel_id  # None = todos os painéis

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Só quem pediu o reset pode confirmar.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Sim, apagar tudo", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        stock = get_guild_stock(self.guild_id)
        if self.panel_id is None:
            apagados = len(stock)
            stock.clear()
        else:
            ids = [pid for pid, p in stock.items() if p.get("painel_id") == self.panel_id]
            apagados = len(ids)
            for pid in ids:
                del stock[pid]
        save_json(STOCK_FILE, stock_data)
        await interaction.response.edit_message(content=f"🗑️ Pronto! {apagados} produto(s) apagado(s) do estoque.", view=None)
        await refresh_panels(interaction.client, self.guild_id)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelado — nada foi apagado.", view=None)


MAX_PRODUTOS_POR_PAINEL = 25  # limite do Discord: um menu de seleção aceita no máximo 25 opções


class EstoqueGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="estoque",
            description="Gerencia o estoque de produtos de cada painel de vendas",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode gerenciar o estoque.")

    @app_commands.command(name="adicionar", description="Adiciona um novo produto a um painel de vendas")
    @app_commands.describe(
        nome="Nome do produto",
        preco="Preço em reais (ex: 19.90)",
        quantidade="Quantidade disponível em estoque",
        descricao="Descrição do produto",
        painel="Em qual painel de vendas esse produto vai aparecer",
    )
    async def adicionar(
        self,
        interaction: discord.Interaction,
        nome: str,
        preco: float,
        quantidade: int,
        descricao: str,
        painel: str = None,
    ):
        panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
        if erro:
            await interaction.response.send_message(erro, ephemeral=True)
            return

        stock = get_guild_stock(interaction.guild_id)
        if find_product(stock, panel_id, nome)[0]:
            await interaction.response.send_message(
                "Já existe um produto com esse nome nesse painel. Use /estoque editar.", ephemeral=True
            )
            return

        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("premium") and len(stock) >= FREE_STOCK_LIMIT:
            await interaction.response.send_message(
                f"🔒 O plano grátis permite até {FREE_STOCK_LIMIT} produtos. "
                "Resgate uma key premium em /configurar pra cadastrar produtos ilimitados.",
                ephemeral=True,
            )
            return

        no_painel = sum(1 for p in stock.values() if p.get("painel_id") == panel_id)
        if no_painel >= MAX_PRODUTOS_POR_PAINEL:
            await interaction.response.send_message(
                f"Esse painel já tem {MAX_PRODUTOS_POR_PAINEL} produtos, que é o máximo que o Discord "
                "permite num menu. Crie outro painel com /painel vendas pra continuar.",
                ephemeral=True,
            )
            return

        pid = f"{panel_id}:{slugify(nome)[:60]}"
        stock[pid] = {
            "nome": nome,
            "preco": preco,
            "quantidade": quantidade,
            "descricao": descricao,
            "painel_id": panel_id,
        }
        save_json(STOCK_FILE, stock_data)
        await interaction.response.defer(ephemeral=True)
        await refresh_panels(interaction.client, interaction.guild_id)
        await interaction.followup.send(f"Produto **{nome}** adicionado com sucesso ✅", ephemeral=True)

    @adicionar.autocomplete("painel")
    async def adicionar_painel_ac(self, interaction: discord.Interaction, current: str):
        return await painel_autocomplete(interaction, current)

    @app_commands.command(name="remover", description="Remove um produto de um painel de vendas")
    @app_commands.describe(nome="Nome do produto", painel="De qual painel de vendas remover")
    async def remover(self, interaction: discord.Interaction, nome: str, painel: str = None):
        panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
        if erro:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        stock = get_guild_stock(interaction.guild_id)
        pid, _ = find_product(stock, panel_id, nome)
        if not pid:
            await interaction.response.send_message("Produto não encontrado nesse painel.", ephemeral=True)
            return
        del stock[pid]
        save_json(STOCK_FILE, stock_data)
        await interaction.response.defer(ephemeral=True)
        await refresh_panels(interaction.client, interaction.guild_id)
        await interaction.followup.send(f"Produto **{nome}** removido ✅", ephemeral=True)

    @remover.autocomplete("painel")
    async def remover_painel_ac(self, interaction: discord.Interaction, current: str):
        return await painel_autocomplete(interaction, current)

    @remover.autocomplete("nome")
    async def remover_nome_ac(self, interaction: discord.Interaction, current: str):
        return await produto_autocomplete(interaction, current)

    @app_commands.command(name="editar", description="Edita um produto de um painel de vendas")
    @app_commands.describe(
        nome="Nome do produto",
        preco="Novo preço (opcional)",
        quantidade="Nova quantidade (opcional)",
        descricao="Nova descrição (opcional)",
        painel="Em qual painel de vendas está o produto",
    )
    async def editar(
        self,
        interaction: discord.Interaction,
        nome: str,
        preco: float = None,
        quantidade: int = None,
        descricao: str = None,
        painel: str = None,
    ):
        panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
        if erro:
            await interaction.response.send_message(erro, ephemeral=True)
            return
        stock = get_guild_stock(interaction.guild_id)
        pid, produto = find_product(stock, panel_id, nome)
        if not pid:
            await interaction.response.send_message("Produto não encontrado nesse painel.", ephemeral=True)
            return
        if preco is not None:
            produto["preco"] = preco
        if quantidade is not None:
            produto["quantidade"] = quantidade
        if descricao is not None:
            produto["descricao"] = descricao
        save_json(STOCK_FILE, stock_data)
        await interaction.response.defer(ephemeral=True)
        await refresh_panels(interaction.client, interaction.guild_id)
        await interaction.followup.send(f"Produto **{nome}** atualizado ✅", ephemeral=True)

    @editar.autocomplete("painel")
    async def editar_painel_ac(self, interaction: discord.Interaction, current: str):
        return await painel_autocomplete(interaction, current)

    @editar.autocomplete("nome")
    async def editar_nome_ac(self, interaction: discord.Interaction, current: str):
        return await produto_autocomplete(interaction, current)

    @app_commands.command(name="listar", description="Lista os produtos de cada painel de vendas")
    @app_commands.describe(painel="Ver só um painel (opcional — sem isso mostra todos)")
    async def listar(self, interaction: discord.Interaction, painel: str = None):
        panels = list_sales_panels(interaction.guild_id)
        if not panels:
            await interaction.response.send_message(
                "Você ainda não tem nenhum painel de vendas. Crie um com /painel vendas.", ephemeral=True
            )
            return
        if painel:
            panels = [p for p in panels if str(p["message_id"]) == painel]
            if not panels:
                await interaction.response.send_message("Painel não encontrado.", ephemeral=True)
                return

        stock = get_guild_stock(interaction.guild_id)
        embed = discord.Embed(title="📦 Estoque por painel", color=discord.Color.blurple())
        for p in panels[:25]:
            pid_painel = str(p["message_id"])
            linhas = []
            for prod in stock.values():
                if prod.get("painel_id") != pid_painel:
                    continue
                qtd = prod["quantidade"]
                estoque = "esgotado" if qtd <= 0 else f"estoque {qtd}"
                linhas.append(f"• **{prod['nome']}** — R$ {prod['preco']:.2f} ({estoque})")
            texto = "\n".join(linhas) or "Nenhum produto ainda."
            if len(texto) > 1000:
                texto = texto[:997] + "..."
            embed.add_field(name=panel_label(interaction.guild, p), value=texto, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @listar.autocomplete("painel")
    async def listar_painel_ac(self, interaction: discord.Interaction, current: str):
        return await painel_autocomplete(interaction, current)

    @app_commands.command(name="resetar", description="Apaga TODOS os produtos do estoque (pede confirmação)")
    @app_commands.describe(painel="Apagar só os produtos desse painel (sem isso, apaga os de todos os painéis)")
    async def resetar(self, interaction: discord.Interaction, painel: str = None):
        stock = get_guild_stock(interaction.guild_id)
        if painel:
            if painel not in {str(p["message_id"]) for p in list_sales_panels(interaction.guild_id)}:
                await interaction.response.send_message("Painel não encontrado.", ephemeral=True)
                return
            total = sum(1 for p in stock.values() if p.get("painel_id") == painel)
            escopo = "do painel escolhido"
        else:
            total = len(stock)
            escopo = "de **todos** os painéis"

        if total == 0:
            await interaction.response.send_message("Não tem nenhum produto pra apagar.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"⚠️ Isso vai apagar **{total} produto(s)** {escopo}, com todo o estoque deles. "
            "**Não dá pra desfazer.** O histórico de vendas (/saldo) continua guardado.\n\nConfirma?",
            view=ResetEstoqueView(interaction.user.id, interaction.guild_id, painel),
            ephemeral=True,
        )

    @resetar.autocomplete("painel")
    async def resetar_painel_ac(self, interaction: discord.Interaction, current: str):
        return await painel_autocomplete(interaction, current)


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

async def reset_select_message(interaction: discord.Interaction, view: discord.ui.View):
    """Reedita a mensagem do painel com um menu novo. Sem isso o Discord continua
    mostrando o ✓ na última opção escolhida, como se o ticket ainda estivesse aberto."""
    if interaction.message is None:
        return
    try:
        await interaction.message.edit(view=view)
    except discord.HTTPException:
        pass


class ProductSelect(discord.ui.Select):
    def __init__(self, guild_id: int, panel_id: str | None = None):
        stock = get_guild_stock(guild_id)
        options = []
        for pid, p in stock.items():
            if panel_id is not None and p.get("painel_id") != panel_id:
                continue  # produto de outro painel
            estoque = "Esgotado" if p["quantidade"] <= 0 else p["quantidade"]
            options.append(
                discord.SelectOption(
                    label=p["nome"][:100],
                    description=f"R$ {p['preco']:.2f} | Estoque: {estoque}"[:100],
                    value=pid,
                )
            )
            if len(options) >= MAX_PRODUTOS_POR_PAINEL:
                break
        if not options:
            options = [discord.SelectOption(label="Sem produtos disponíveis", value="none")]
        super().__init__(
            placeholder="Selecione um produto...",
            options=options,
            custom_id="painel_product_select",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await self._handle(interaction)
        finally:
            await reset_select_message(interaction, ProductSelectView(interaction.guild_id, str(interaction.message.id)))

    async def _handle(self, interaction: discord.Interaction):
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
    def __init__(self, guild_id: int, panel_id: str | None = None):
        super().__init__(timeout=None)
        self.add_item(ProductSelect(guild_id, panel_id))


class PanelModal(discord.ui.Modal, title="Criar Painel de Vendas"):
    titulo = discord.ui.TextInput(label="Título do painel", max_length=256)
    descricao = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        cor = discord.Color(cfg["cor_embed"]) if cfg.get("cor_embed") is not None else discord.Color.gold()

        # Embed único — barra colorida contínua do título até o banner, sem
        # parecer duas caixas separadas. O banner fica embaixo do texto.
        embed = discord.Embed(title=self.titulo.value, description=self.descricao.value, color=cor)
        if self.banner_url:
            embed.set_image(url=self.banner_url)

        # Publica como mensagem normal do canal (não como resposta do comando),
        # assim não aparece "usou /painel" acima da mensagem.
        # Cada painel tem o seu próprio estoque: o id do painel é o id dessa mensagem.
        panel_message = await interaction.channel.send(embed=embed, view=ProductSelectView(interaction.guild_id, "novo"))
        add_panel_record(
            interaction.guild_id, interaction.channel_id, panel_message.id,
            self.banner_url, self.titulo.value, self.descricao.value,
        )
        migrate_legacy_products()  # se existirem produtos antigos sem painel, o 1º painel adota eles
        await panel_message.edit(view=ProductSelectView(interaction.guild_id, str(panel_message.id)))

        tem_produtos = any(
            p.get("painel_id") == str(panel_message.id) for p in get_guild_stock(interaction.guild_id).values()
        )
        aviso = (
            ""
            if tem_produtos
            else "\n\n⚠️ Esse painel começou **vazio** (cada painel tem o seu próprio estoque). "
            "Use /estoque adicionar e escolha este painel no campo **painel** (só você vê este aviso)."
        )
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
        try:
            if self.values[0] == "none":
                await interaction.response.send_message(
                    "Nenhum tipo de atendimento disponível no momento.", ephemeral=True
                )
                return
            await create_help_ticket(interaction, self.values[0])
        finally:
            await reset_select_message(interaction, HelpTicketSelectView(interaction.guild_id))


class HelpTicketSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(HelpTicketSelect(guild_id))


class HelpPanelModal(discord.ui.Modal, title="Criar Painel de Ticket de Ajuda"):
    titulo = discord.ui.TextInput(label="Título do painel", max_length=256)
    descricao = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        options = get_guild_help_options(interaction.guild_id)
        cfg = get_guild_config(interaction.guild_id)
        cor = discord.Color(cfg["cor_embed"]) if cfg.get("cor_embed") is not None else discord.Color.blurple()

        embed = discord.Embed(title=self.titulo.value, description=self.descricao.value, color=cor)
        if self.banner_url:
            embed.set_image(url=self.banner_url)
        view = HelpTicketSelectView(interaction.guild_id)

        panel_message = await interaction.channel.send(embed=embed, view=view)
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
    @app_commands.describe(banner="Imagem de banner para o final do painel (opcional)")
    async def vendas(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url if banner else None
        await interaction.response.send_modal(PanelModal(banner_url))

    @app_commands.command(name="ticket", description="Cria o painel de ticket de ajuda neste canal")
    @app_commands.describe(banner="Imagem de banner para o final do painel (opcional)")
    async def ticket(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url if banner else None
        await interaction.response.send_modal(HelpPanelModal(banner_url))


# ----------------------------------------------------------------------------
# /mensagem — manda uma mensagem personalizada (texto livre + banner opcional)
# ----------------------------------------------------------------------------

class MensagemModal(discord.ui.Modal, title="Enviar Mensagem"):
    titulo = discord.ui.TextInput(label="Título (opcional)", required=False, max_length=256)
    texto = discord.ui.TextInput(
        label="Mensagem",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        placeholder="Dica: pra um link clicável, escreva [texto do link](https://exemplo.com)",
    )

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(description=self.texto.value, color=discord.Color.blurple())
        if self.titulo.value:
            embed.title = self.titulo.value
        if self.banner_url:
            embed.set_image(url=self.banner_url)

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("Mensagem enviada ✅", ephemeral=True)


@bot.tree.command(name="mensagem", description="Envia uma mensagem personalizada neste canal, com banner opcional")
@app_commands.describe(banner="Imagem de banner para o final da mensagem (opcional)")
@app_commands.default_permissions(administrator=True)
@require_owner()
async def mensagem(interaction: discord.Interaction, banner: discord.Attachment = None):
    banner_url = banner.url if banner else None
    await interaction.response.send_modal(MensagemModal(banner_url))


# ----------------------------------------------------------------------------
# /personalizar — recursos premium (precisa de key resgatada em /configurar)
# ----------------------------------------------------------------------------

class CorModal(discord.ui.Modal, title="Cor dos painéis"):
    cor = discord.ui.TextInput(label="Cor em hexadecimal", placeholder="Ex: FF5733", max_length=7)

    async def on_submit(self, interaction: discord.Interaction):
        texto = self.cor.value.strip().lstrip("#")
        try:
            valor = int(texto, 16)
            if not (0 <= valor <= 0xFFFFFF):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Cor inválida — use um código hexadecimal, tipo `FF5733` ou `#FF5733`.", ephemeral=True
            )
            return
        cfg = get_guild_config(interaction.guild_id)
        cfg["cor_embed"] = valor
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)
        await interaction.response.send_message(f"Cor dos painéis atualizada ✅ (#{texto.upper()})", ephemeral=True)


class BoasVindasModal(discord.ui.Modal, title="Mensagem de Boas-vindas"):
    titulo = discord.ui.TextInput(label="Título (opcional)", required=False, max_length=256)
    texto = discord.ui.TextInput(label="Mensagem", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        cfg["boasvindas_titulo"] = self.titulo.value or None
        cfg["boasvindas_texto"] = self.texto.value
        if self.banner_url:
            cfg["boasvindas_banner_url"] = self.banner_url
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)

        aviso = "" if cfg.get("canal_boasvindas_id") else "\n\n⚠️ Defina o canal de boas-vindas em /configurar pra ativar."
        await interaction.response.send_message(f"Mensagem de boas-vindas salva ✅{aviso}", ephemeral=True)


class PersonalizarGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="personalizar",
            description="[Premium] Personaliza a aparência do bot neste servidor",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in OWNER_USER_IDS:
            return True
        if not is_owner(interaction):
            raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")
        cfg = get_guild_config(interaction.guild_id)
        if not cfg.get("premium"):
            raise app_commands.CheckFailure(
                "🔒 Este é um recurso premium. Resgate uma key em /configurar para desbloquear."
            )
        return True

    @app_commands.command(name="nome", description="Muda o apelido do bot neste servidor")
    @app_commands.describe(nome="Novo nome/apelido do bot neste servidor")
    async def nome(self, interaction: discord.Interaction, nome: str):
        try:
            await interaction.guild.me.edit(nick=nome)
            await interaction.response.send_message(f"Nome do bot alterado para **{nome}** ✅", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão pra mudar meu apelido aqui — preciso da permissão 'Gerenciar Apelidos', "
                "e meu cargo precisa estar acima de quem eu tento mudar (no caso, eu mesmo).",
                ephemeral=True,
            )

    @app_commands.command(name="foto", description="Muda a foto de perfil do bot neste servidor")
    @app_commands.describe(foto="Nova imagem de perfil do bot neste servidor")
    async def foto(self, interaction: discord.Interaction, foto: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        try:
            image_bytes = await foto.read()
            await interaction.guild.me.edit(avatar=image_bytes)
            await interaction.followup.send("Foto do bot alterada neste servidor ✅", ephemeral=True)
        except TypeError:
            await interaction.followup.send(
                "A versão do discord.py instalada nesse host ainda não suporta foto por servidor — "
                "atualize com `pip install -U discord.py` e tente de novo.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(f"Não consegui trocar a foto: {e}", ephemeral=True)

    @app_commands.command(name="banner", description="Muda o banner de perfil do bot neste servidor")
    @app_commands.describe(banner="Nova imagem de banner de perfil do bot neste servidor")
    async def banner(self, interaction: discord.Interaction, banner: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        try:
            image_bytes = await banner.read()
            await interaction.guild.me.edit(banner=image_bytes)
            await interaction.followup.send("Banner do bot alterado neste servidor ✅", ephemeral=True)
        except TypeError:
            await interaction.followup.send(
                "A versão do discord.py instalada nesse host ainda não suporta banner por servidor — "
                "atualize com `pip install -U discord.py` e tente de novo.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.followup.send(f"Não consegui trocar o banner: {e}", ephemeral=True)

    @app_commands.command(name="cor", description="Muda a cor dos painéis de vendas/ticket neste servidor")
    async def cor(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CorModal())

    @app_commands.command(name="boasvindas", description="Configura a mensagem automática pra quem entra no servidor")
    @app_commands.describe(banner="Imagem de banner para o final da mensagem (opcional)")
    async def boasvindas(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url if banner else None
        await interaction.response.send_modal(BoasVindasModal(banner_url))


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

    # Guarda o produto/comprador num arquivo nosso (não depende só do tópico do canal)
    ticket_info_data.setdefault(gid, {})[str(channel.id)] = {"produto": product_id, "comprador": interaction.user.id}
    save_json(TICKET_INFO_FILE, ticket_info_data)

    embed = discord.Embed(title=f"🛒 Pedido: {product['nome']}", color=discord.Color.green())
    embed.add_field(name="💰 Preço", value=f"R$ {product['preco']:.2f}", inline=True)
    embed.add_field(name="📝 Descrição", value=product["descricao"], inline=False)
    embed.set_footer(text=f"Comprador: {interaction.user} • Tem um cupom? Clique em 🏷️ Resgatar Cupom")
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

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


async def remove_ticket_record(guild_id: int, channel_id: int, concluido: bool = False):
    gid = str(guild_id)
    if not concluido:
        # ticket fechado sem pagamento: devolve a vaga do cupom pra outra pessoa usar
        liberar_cupom_do_ticket(guild_id, channel_id)
    user_tickets = tickets_data.get(gid, {})
    for uid, cid in list(user_tickets.items()):
        if cid == channel_id:
            del user_tickets[uid]
    tickets_data[gid] = user_tickets
    save_json(TICKETS_FILE, tickets_data)
    if ticket_info_data.get(gid, {}).pop(str(channel_id), None) is not None:
        save_json(TICKET_INFO_FILE, ticket_info_data)


def get_ticket_info(guild_id: int, channel_id: int) -> dict:
    return ticket_info_data.get(str(guild_id), {}).get(str(channel_id), {})


# ----------------------------------------------------------------------------
# Cupons de desconto
# ----------------------------------------------------------------------------

def save_coupons():
    save_json(COUPONS_FILE, coupons_data)


def get_guild_coupons(guild_id: int) -> dict:
    return coupons_data.setdefault(str(guild_id), {})


def normalizar_cupom(nome: str) -> str:
    return re.sub(r"[^A-Z0-9_-]", "", (nome or "").strip().upper())


def cupom_expirado(c: dict) -> bool:
    return time.time() >= c["expira_em"]


def preco_do_ticket(info: dict, product: dict) -> float:
    """Preço que o comprador realmente paga (com o desconto do cupom, se ele resgatou um)."""
    return round(float(info.get("preco_final", product["preco"])), 2)


def liberar_cupom_do_ticket(guild_id: int, channel_id: int):
    """Se o ticket tinha um cupom resgatado e não foi pago, devolve a vaga do cupom."""
    info = get_ticket_info(guild_id, channel_id)
    codigo = info.get("cupom")
    buyer = info.get("comprador")
    if not codigo:
        return
    c = get_guild_coupons(guild_id).get(codigo)
    if c and buyer in c["usos"]:
        c["usos"].remove(buyer)
        save_coupons()


def barra_progresso(usados: int, limite: int, tam: int = 10) -> str:
    cheio = 0 if limite <= 0 else min(tam, round(tam * usados / limite))
    return "▰" * cheio + "▱" * (tam - cheio)


def status_cupom(c: dict) -> str:
    if cupom_expirado(c):
        return "⌛ Expirado"
    if len(c["usos"]) >= c["limite"]:
        return "🚫 Esgotado"
    return "🟢 Ativo"


def embed_cupom(codigo: str, c: dict, titulo: str = "🏷️ Cupom de desconto") -> discord.Embed:
    usados, limite = len(c["usos"]), c["limite"]
    ativo = status_cupom(c) == "🟢 Ativo"
    embed = discord.Embed(
        title=titulo,
        description=f"## `{codigo}`\n### 💸 {c['desconto']}% de desconto",
        color=discord.Color.green() if ativo else discord.Color.dark_grey(),
    )
    embed.add_field(name="📊 Usos", value=f"{barra_progresso(usados, limite)}\n**{usados}/{limite}** pessoas", inline=True)
    embed.add_field(name="⏰ Expira", value=f"<t:{int(c['expira_em'])}:R>\n<t:{int(c['expira_em'])}:f>", inline=True)
    embed.add_field(name="📌 Status", value=status_cupom(c), inline=True)
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def embed_erro_cupom(msg: str) -> discord.Embed:
    return discord.Embed(title="🏷️ Não deu pra usar o cupom", description=msg, color=discord.Color.red())


def validar_e_resgatar_cupom(guild_id: int, channel_id: int, user_id: int, codigo: str, product: dict):
    """Valida o cupom e aplica no ticket. Retorna (ok, mensagem, info_do_ticket)."""
    info = get_ticket_info(guild_id, channel_id)
    if not info:
        return False, "Não achei os dados deste ticket.", None
    if info.get("cupom"):
        return False, f"Este ticket já está usando o cupom **{info['cupom']}**.", None

    codigo = normalizar_cupom(codigo)
    c = get_guild_coupons(guild_id).get(codigo)
    if not c:
        return False, "❌ Esse cupom não existe. Confira o nome e tente de novo.", None
    if cupom_expirado(c):
        return False, "⌛ Esse cupom já expirou.", None
    if user_id in c["usos"]:
        return False, "Você já usou esse cupom.", None
    if len(c["usos"]) >= c["limite"]:
        return False, "😕 Esse cupom já atingiu o limite de usos.", None

    # tudo certo: reserva a vaga e congela o preço com desconto no ticket
    c["usos"].append(user_id)
    save_coupons()
    preco_original = float(product["preco"])
    preco_final = round(preco_original * (100 - c["desconto"]) / 100, 2)
    info["cupom"] = codigo
    info["desconto"] = c["desconto"]
    info["preco_original"] = preco_original
    info["preco_final"] = preco_final
    save_json(TICKET_INFO_FILE, ticket_info_data)
    return True, "", info


# Tickets que já estão sendo concluídos — evita baixar o estoque 2x se clicarem 2 vezes
concluindo_tickets: set = set()


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


class ResgatarCupomModal(discord.ui.Modal, title="🏷️ Resgatar cupom"):
    codigo = discord.ui.TextInput(
        label="Nome do cupom", placeholder="Ex: PROMO10", min_length=1, max_length=32, required=True
    )

    def __init__(self, mensagem_ticket: discord.Message | None):
        super().__init__()
        self.mensagem_ticket = mensagem_ticket

    async def on_submit(self, interaction: discord.Interaction):
        gid, cid = interaction.guild_id, interaction.channel_id
        info = get_ticket_info(gid, cid)
        product_id = info.get("produto") or getattr(interaction.channel, "topic", None)
        product = get_guild_stock(gid).get(product_id) if product_id else None
        if not product:
            await interaction.response.send_message(
                embed=embed_erro_cupom("Não consegui identificar o produto deste ticket."), ephemeral=True
            )
            return

        ok, erro, info = validar_e_resgatar_cupom(gid, cid, interaction.user.id, self.codigo.value, product)
        if not ok:
            await interaction.response.send_message(embed=embed_erro_cupom(erro), ephemeral=True)
            return

        economia = info["preco_original"] - info["preco_final"]

        # atualiza o embed do pedido (preço riscado + cupom + cor dourada)
        msg = self.mensagem_ticket or interaction.message
        if msg and msg.embeds:
            embed = msg.embeds[0]
            valor = f"~~R$ {info['preco_original']:.2f}~~\n**R$ {info['preco_final']:.2f}**"
            idx = next((i for i, f in enumerate(embed.fields) if f.name.endswith("Preço") or f.name == "Preço"), None)
            if idx is not None:
                embed.set_field_at(idx, name="💰 Preço", value=valor, inline=True)
            else:
                embed.add_field(name="💰 Preço", value=valor, inline=True)
            embed.add_field(
                name="🏷️ Cupom",
                value=f"`{info['cupom']}`\n**-{info['desconto']}%** (economia de R$ {economia:.2f})",
                inline=True,
            )
            embed.color = discord.Color.gold()
            try:
                await msg.edit(embed=embed)
            except discord.HTTPException:
                pass

        # aviso bonito pra todo mundo do ticket ver
        aviso = discord.Embed(
            title="🎉 Cupom aplicado!",
            description=f"O cupom `{info['cupom']}` foi resgatado por {interaction.user.mention}.",
            color=discord.Color.gold(),
        )
        aviso.add_field(name="Antes", value=f"~~R$ {info['preco_original']:.2f}~~", inline=True)
        aviso.add_field(name="Desconto", value=f"**-{info['desconto']}%**", inline=True)
        aviso.add_field(name="Agora", value=f"**R$ {info['preco_final']:.2f}**", inline=True)
        aviso.add_field(name="💚 Você economizou", value=f"R$ {economia:.2f}", inline=False)
        aviso.set_thumbnail(url=interaction.user.display_avatar.url)
        aviso.set_footer(text="O valor do ticket já foi atualizado automaticamente.")
        aviso.timestamp = datetime.now(timezone.utc)
        await interaction.response.send_message(embed=aviso)

        await send_log(
            gid,
            f"🏷️ {interaction.user.mention} usou o cupom **{info['cupom']}** em {interaction.channel.mention} "
            f"(R$ {info['preco_original']:.2f} → R$ {info['preco_final']:.2f}).",
        )


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

        canal_id = interaction.channel_id
        if canal_id in concluindo_tickets:
            await interaction.response.send_message("Este pagamento já está sendo concluído.", ephemeral=True)
            return
        concluindo_tickets.add(canal_id)

        try:
            # 1) Descobre produto e comprador (só memória — rápido). O produto vem do nosso
            #    registro; o tópico do canal fica como plano B (tickets criados antes dessa versão).
            info = get_ticket_info(interaction.guild_id, canal_id)
            product_id = info.get("produto") or getattr(interaction.channel, "topic", None)
            stock = get_guild_stock(interaction.guild_id)
            product = stock.get(product_id) if product_id else None
            buyer_id = info.get("comprador") or get_ticket_owner_id(interaction.guild_id, canal_id)

            # 2) Responde ao Discord NA HORA (ele cancela a interação se passar de 3 segundos)
            aviso = (
                ""
                if product
                else "\n⚠️ Não consegui identificar o produto desse ticket (ou ele foi removido do estoque): "
                "o estoque e o saldo **não** foram atualizados."
            )
            await interaction.response.send_message(
                f"✅ Pagamento concluído! Este ticket será fechado em alguns segundos...{aviso}"
            )

            # 3) Trabalho mais lento — uma falha aqui nunca pode impedir o ticket de fechar
            try:
                if product:
                    if product["quantidade"] > 0:
                        product["quantidade"] -= 1
                        save_json(STOCK_FILE, stock_data)
                    preco_pago = preco_do_ticket(info, product)
                    record_sale(interaction.guild_id, product["nome"], preco_pago, buyer_id or 0, interaction.user.id)

                    comprador = f"<@{buyer_id}>" if buyer_id else "(desconhecido)"
                    await send_log(
                        interaction.guild_id,
                        message=(
                            f"✅ Venda concluída: **{product['nome']}** (R$ {preco_pago:.2f}"
                            f"{' com cupom ' + info['cupom'] if info.get('cupom') else ''}) — "
                            f"comprador {comprador}, atendido por {interaction.user.mention}."
                        ),
                    )
                    entrega_embed = discord.Embed(title=f"📦 {product['nome']}", color=discord.Color.green())
                    entrega_embed.add_field(name="Preço", value=f"R$ {preco_pago:.2f}", inline=True)
                    if info.get("cupom"):
                        entrega_embed.add_field(
                            name="Cupom", value=f"{info['cupom']} (-{info['desconto']}%)", inline=True
                        )
                    entrega_embed.add_field(name="Descrição", value=product["descricao"], inline=False)
                    entrega_embed.set_footer(text=f"Comprador: {comprador} | Atendido por: {interaction.user}")
                    await send_delivery_log(interaction.guild_id, entrega_embed)
                    await refresh_panels(interaction.client, interaction.guild_id)
            except Exception as erro:  # noqa: BLE001
                print(f"[concluir] erro ao atualizar estoque/logs: {erro!r}")

            await asyncio.sleep(5)
            try:
                await interaction.channel.delete()
            finally:
                await remove_ticket_record(interaction.guild_id, canal_id, concluido=True)
                if product and buyer_id:
                    await send_rating_request(interaction.guild_id, buyer_id, interaction.user.id, product["nome"])
        finally:
            concluindo_tickets.discard(canal_id)

    @discord.ui.button(label="🏷️ Resgatar Cupom", style=discord.ButtonStyle.blurple, custom_id="ticket_resgatar_cupom")
    async def resgatar_cupom(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = get_ticket_info(interaction.guild_id, interaction.channel_id)
        buyer_id = info.get("comprador") or get_ticket_owner_id(interaction.guild_id, interaction.channel_id)
        if interaction.user.id != buyer_id:
            await interaction.response.send_message(
                embed=embed_erro_cupom("Só quem abriu este ticket pode resgatar cupom."), ephemeral=True
            )
            return
        if info.get("cupom"):
            await interaction.response.send_message(
                embed=embed_erro_cupom(f"Este ticket já está usando o cupom `{info['cupom']}`."), ephemeral=True
            )
            return
        await interaction.response.send_modal(ResgatarCupomModal(interaction.message))

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
# Sorteios — botão de participar, sorteio automático e ticket do prêmio
# ----------------------------------------------------------------------------

TICKET_SORTEIO_CATEGORY_NAME = "🎁 Ticket Sorteios"
SORTEIO_TICK_SEGUNDOS = 10  # de quanto em quanto tempo o bot confere se algum sorteio acabou
SORTEIO_MIN_SEGUNDOS = 30
SORTEIO_MAX_SEGUNDOS = 30 * 24 * 3600
SORTEIO_RETENCAO_SEGUNDOS = 30 * 24 * 3600  # sorteios antigos são esquecidos depois disso

sorteio_task = None

_UNIDADES_TEMPO = {
    "d": 86400, "dia": 86400, "dias": 86400,
    "h": 3600, "hora": 3600, "horas": 3600,
    "m": 60, "min": 60, "minuto": 60, "minutos": 60,
    "s": 1, "seg": 1, "segundo": 1, "segundos": 1,
}


def parse_duracao(texto: str) -> int | None:
    """'30m' -> 1800, '1h30m' -> 5400, '2 dias' -> 172800. None se não entender."""
    t = (texto or "").strip().lower()
    if not re.fullmatch(r"(?:\s*\d+\s*[a-z]+)+\s*", t):
        return None
    total = 0
    for n, unidade in re.findall(r"(\d+)\s*([a-z]+)", t):
        if unidade not in _UNIDADES_TEMPO:
            return None
        total += int(n) * _UNIDADES_TEMPO[unidade]
    return total or None


def save_giveaways():
    save_json(GIVEAWAYS_FILE, giveaways_data)


def get_guild_giveaways(guild_id: int) -> dict:
    return giveaways_data.setdefault(str(guild_id), {})


def get_giveaway(guild_id: int, sid) -> dict | None:
    return giveaways_data.get(str(guild_id), {}).get(str(sid))


def find_round_by_message(guild_id: int, message_id: int):
    for g in giveaways_data.get(str(guild_id), {}).values():
        for rodada in g.get("rodadas", []):
            if rodada.get("aviso_msg_id") == message_id:
                return g, rodada
    return None, None


def find_giveaway_by_ticket(guild_id: int, channel_id: int):
    for g in giveaways_data.get(str(guild_id), {}).values():
        for uid, cid in g.get("tickets", {}).items():
            if cid == channel_id:
                return g, int(uid)
    return None, None


def plural_ganhadores(n: int) -> str:
    return f"{n} ganhador" + ("es" if n != 1 else "")


def sortear(candidatos: list, qtd: int, excluir: set | None = None, pesos: dict | None = None) -> list:
    """Sorteia 'qtd' pessoas, sem repetir. 'pesos' = quantas entradas cada pessoa tem
    (quem não está em 'pesos' vale 1). Quanto mais entradas, mais chance."""
    excluir = excluir or set()
    pesos = pesos or {}
    pool = [u for u in dict.fromkeys(candidatos) if u not in excluir]
    escolhidos = []
    while pool and len(escolhidos) < qtd:
        escolhido = random.choices(pool, weights=[max(1, pesos.get(u, 1)) for u in pool], k=1)[0]
        escolhidos.append(escolhido)
        pool.remove(escolhido)
    return escolhidos


def entradas_do_membro(g: dict, member) -> tuple:
    """(quantas entradas a pessoa tem, id do cargo que deu isso). Vale o MAIOR cargo, não soma."""
    melhor, cargo_id = 1, None
    tabela = g.get("entradas_extras") or {}
    for cargo in member.roles:
        n = tabela.get(str(cargo.id), 1)
        if n > melhor:
            melhor, cargo_id = n, cargo.id
    return melhor, cargo_id


def todos_ganhadores(g: dict) -> list:
    return list(g.get("ganhadores", []))


# ---------- embeds ----------

def embed_sorteio_ativo(g: dict) -> discord.Embed:
    partes = []
    if g.get("descricao"):
        partes.append(g["descricao"])
    partes.append("Clique em **Participar** para concorrer!")
    if g.get("cargo_requerido_id"):
        partes.append(f"🔒 Requisito: ter o cargo <@&{g['cargo_requerido_id']}>")
    fim = int(g["termina_em"])
    embed = discord.Embed(title=f"🎉 {g['premio']}", description="\n\n".join(partes), color=discord.Color.gold())
    embed.add_field(name="🏆 Ganhadores", value=str(g["ganhadores_qtd"]), inline=True)
    embed.add_field(name="⏰ Termina", value=f"<t:{fim}:R>\n<t:{fim}:f>", inline=True)
    embed.add_field(name="🎖️ Organizado por", value=f"<@{g['organizador_id']}>", inline=False)
    extras = sorted(((int(c), n) for c, n in (g.get("entradas_extras") or {}).items() if n > 1), key=lambda x: -x[1])
    if extras:
        embed.add_field(
            name="✨ Entradas extras",
            value="\n".join(f"<@&{c}> → **{n}** entradas" for c, n in extras),
            inline=False,
        )
    embed.set_footer(text=f"{plural_ganhadores(g['ganhadores_qtd'])} • Termina em")
    embed.timestamp = datetime.fromtimestamp(g["termina_em"], tz=timezone.utc)
    if g.get("banner_url"):
        embed.set_image(url=g["banner_url"])
    return embed


def embed_sorteio_encerrado(g: dict) -> discord.Embed:
    ganhadores = todos_ganhadores(g)
    quando = g.get("encerrou_em") or time.time()
    embed = discord.Embed(
        title=f"🎉 {g['premio']}",
        description="Este sorteio foi **encerrado**!\nAs inscrições estão fechadas — participe do próximo.",
        color=discord.Color(0x979C9F),
    )
    embed.add_field(
        name="🏆 Ganhadores",
        value=" ".join(f"<@{u}>" for u in ganhadores) or "Ninguém participou 😢",
        inline=False,
    )
    embed.add_field(name="👥 Participantes", value=str(len(g["participantes"])), inline=True)
    embed.add_field(name="⏰ Encerrou", value=f"<t:{int(quando)}:R>", inline=True)
    embed.add_field(name="🎖️ Organizado por", value=f"<@{g['organizador_id']}>", inline=False)
    embed.set_footer(text=f"{plural_ganhadores(len(ganhadores))} • Encerrou em")
    embed.timestamp = datetime.fromtimestamp(quando, tz=timezone.utc)
    if g.get("banner_url"):
        embed.set_image(url=g["banner_url"])
    return embed


def lista_ganhadores(g: dict, rodada: dict, expirado: bool) -> str:
    linhas = []
    for uid in rodada["ganhadores"]:
        if uid in g.get("resgatados", []):
            linhas.append(f"✅ <@{uid}>")
        elif expirado:
            linhas.append(f"❌ ~~<@{uid}>~~ — perdeu o prazo")
        else:
            linhas.append(f"🏆 <@{uid}>")
    return "\n".join(linhas)


def embed_anuncio(g: dict, rodada: dict, expirado: bool = False) -> discord.Embed:
    n = len(rodada["ganhadores"])
    pendentes = [u for u in rodada["ganhadores"] if u not in g.get("resgatados", [])]
    abertura = f"Parabéns {'ao ganhador' if n == 1 else 'aos ganhadores'} de **{g['premio']}**!"
    if not pendentes:
        instrucao = "✅ Todos os ganhadores já abriram o ticket do prêmio."
    elif expirado:
        instrucao = "⏰ O prazo para abrir o ticket acabou."
    else:
        instrucao = (
            "Clique no botão abaixo para abrir o ticket e receber seu prêmio.\n"
            f"⏳ Prazo: <t:{int(rodada['prazo'])}:R> ({g['prazo_minutos']} min)"
        )
    embed = discord.Embed(
        title="🎉 Sorteio Encerrado!",
        description=f"{abertura}\n\n{lista_ganhadores(g, rodada, expirado)}\n\n{instrucao}",
        color=discord.Color.gold(),
    )
    embed.add_field(name="👥 Total de participantes", value=str(len(g["participantes"])), inline=False)
    embed.add_field(name="🎖️ Organizado por", value=f"<@{g['organizador_id']}>", inline=False)
    embed.set_footer(text=f"Você tem {g['prazo_minutos']} minutos para abrir o ticket do prêmio")
    return embed


# ---------- botões ----------

class GiveawayJoinButton(discord.ui.Button):
    def __init__(self, participantes: int = 0, encerrado: bool = False):
        super().__init__(
            label=f"Participar ({participantes})",
            emoji="🎉",
            style=discord.ButtonStyle.secondary if encerrado else discord.ButtonStyle.primary,
            custom_id="sorteio_participar",
            disabled=encerrado,
        )

    async def callback(self, interaction: discord.Interaction):
        g = get_giveaway(interaction.guild_id, interaction.message.id)
        # Depois que o sorteio acaba (ou passa da hora) ninguém mais entra — só no próximo sorteio.
        if not g or g["status"] != "ativo" or time.time() >= g["termina_em"]:
            await interaction.response.send_message(
                "⏰ Esse sorteio já acabou, as inscrições estão fechadas. Participe do próximo!", ephemeral=True
            )
            return

        req = g.get("cargo_requerido_id")
        if req and not any(r.id == req for r in interaction.user.roles):
            await interaction.response.send_message(
                f"🔒 Só quem tem o cargo <@&{req}> pode participar deste sorteio.", ephemeral=True
            )
            return

        uid = interaction.user.id
        if uid in g["participantes"]:
            await interaction.response.send_message(
                "Você já está participando! 🍀 Quer sair do sorteio?",
                view=LeaveView(str(interaction.message.id)),
                ephemeral=True,
            )
            return

        g["participantes"].append(uid)
        save_giveaways()
        await interaction.response.edit_message(view=GiveawayView(len(g["participantes"])))

        n, cargo_id = entradas_do_membro(g, interaction.user)
        extra = f"\n✨ Você tem **{n} entradas** por causa do cargo <@&{cargo_id}>!" if n > 1 else ""
        await interaction.followup.send(f"✅ Você está participando! Boa sorte 🍀{extra}", ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, participantes: int = 0, encerrado: bool = False):
        super().__init__(timeout=None)
        self.add_item(GiveawayJoinButton(participantes, encerrado))


class LeaveView(discord.ui.View):
    def __init__(self, sid: str):
        super().__init__(timeout=120)
        self.sid = sid

    @discord.ui.button(label="Sair do sorteio", style=discord.ButtonStyle.danger)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = get_giveaway(interaction.guild_id, self.sid)
        if g and g["status"] == "ativo" and interaction.user.id in g["participantes"]:
            g["participantes"].remove(interaction.user.id)
            save_giveaways()
            await interaction.response.edit_message(content="Você saiu do sorteio.", view=None)
            await atualizar_mensagem_sorteio(interaction.client, g)
        else:
            await interaction.response.edit_message(content="Esse sorteio já acabou.", view=None)


class ClaimButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Abrir Ticket do Prêmio",
            emoji="🎁",
            style=discord.ButtonStyle.success,
            custom_id="sorteio_resgatar",
        )

    async def callback(self, interaction: discord.Interaction):
        g, rodada = find_round_by_message(interaction.guild_id, interaction.message.id)
        if not g:
            await interaction.response.send_message("Esse sorteio não está mais disponível.", ephemeral=True)
            return

        uid = interaction.user.id
        if uid not in rodada["ganhadores"]:
            await interaction.response.send_message("Esse botão é só para os ganhadores do sorteio.", ephemeral=True)
            return

        if uid in g.setdefault("resgatados", []):
            cid = g.get("tickets", {}).get(str(uid))
            texto = f"Você já abriu o seu ticket: <#{cid}>" if cid else "Você já resgatou o seu prêmio."
            await interaction.response.send_message(texto, ephemeral=True)
            return

        if time.time() >= rodada["prazo"]:
            await interaction.response.send_message(
                f"⏰ O seu prazo para abrir o ticket acabou. Fale com <@{g['organizador_id']}>.", ephemeral=True
            )
            return

        # Marca já, antes de qualquer espera, pra um clique duplo não criar 2 tickets
        g["resgatados"].append(uid)
        save_giveaways()
        await interaction.response.defer(ephemeral=True)
        try:
            canal = await criar_ticket_premio(interaction.guild, g, interaction.user)
        except discord.HTTPException:
            g["resgatados"].remove(uid)
            save_giveaways()
            await interaction.followup.send(
                "Não consegui criar o canal do ticket (falta permissão pro bot). Avise a administração.",
                ephemeral=True,
            )
            return

        g.setdefault("tickets", {})[str(uid)] = canal.id
        save_giveaways()
        await interaction.followup.send(f"🎁 Ticket do prêmio criado: {canal.mention}", ephemeral=True)
        try:
            await interaction.message.edit(embed=embed_anuncio(g, rodada))
        except discord.HTTPException:
            pass


class ClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ClaimButton())


class PremioTicketView(discord.ui.View):
    """Botões dentro do ticket do prêmio — só a equipe usa."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Prêmio entregue", emoji="✅", style=discord.ButtonStyle.success, custom_id="premio_entregue")
    async def entregue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (is_owner(interaction) or is_admin(interaction)):
            await interaction.response.send_message("Apenas a equipe pode marcar o prêmio como entregue.", ephemeral=True)
            return
        g, uid = find_giveaway_by_ticket(interaction.guild_id, interaction.channel_id)
        await interaction.response.send_message("✅ Prêmio marcado como entregue! O ticket fecha em 5 segundos...")
        if g:
            g.setdefault("entregues", []).append(uid)
            save_giveaways()
            await send_log(
                interaction.guild_id,
                message=f"🎁 Prêmio de sorteio entregue: **{g['premio']}** → <@{uid}> (por {interaction.user.mention}).",
            )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Fechar ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="premio_fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (is_owner(interaction) or is_admin(interaction)):
            await interaction.response.send_message("Apenas a equipe pode fechar este ticket.", ephemeral=True)
            return
        g, uid = find_giveaway_by_ticket(interaction.guild_id, interaction.channel_id)
        await interaction.response.send_message("Fechando o ticket em instantes...")
        if g:
            g.get("tickets", {}).pop(str(uid), None)
            save_giveaways()
            await send_log(
                interaction.guild_id,
                message=f"🔒 Ticket do prêmio **{g['premio']}** fechado por {interaction.user.mention} (sem marcar como entregue).",
            )
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete()
        except discord.HTTPException:
            pass


# ---------- ticket do prêmio ----------

async def get_or_create_sorteio_category(guild: discord.Guild, staff_roles: list):
    for cat in guild.categories:
        if cat.name == TICKET_SORTEIO_CATEGORY_NAME:
            return cat
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True),
    }
    for role in staff_roles:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True)
    return await guild.create_category(TICKET_SORTEIO_CATEGORY_NAME, overwrites=overwrites)


async def criar_ticket_premio(guild: discord.Guild, g: dict, member: discord.Member):
    cfg = get_guild_config(guild.id)
    staff = get_staff_roles(guild, cfg)
    categoria = await get_or_create_sorteio_category(guild, staff)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for role in staff:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    nome = f"premio-{member.name}".lower().replace(" ", "-")[:90]
    canal = await guild.create_text_channel(name=nome, category=categoria, overwrites=overwrites)

    embed = discord.Embed(
        title="🎁 Ticket do prêmio",
        description=(
            f"Parabéns {member.mention}! Você ganhou **{g['premio']}**.\n"
            "Um membro da equipe vai te atender aqui para entregar o prêmio."
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(name="🎖️ Organizado por", value=f"<@{g['organizador_id']}>", inline=False)
    mencoes = member.mention + " " + " ".join(r.mention for r in staff)
    await canal.send(content=mencoes, embed=embed, view=PremioTicketView())
    await canal.send("⏳ Aguarde, a equipe já vai te atender.")
    return canal


# ---------- motor do sorteio ----------

async def _buscar_canal(client, canal_id: int):
    canal = client.get_channel(canal_id)
    if canal is not None:
        return canal, "ok"
    try:
        return await client.fetch_channel(canal_id), "ok"
    except discord.NotFound:
        return None, "apagado"
    except discord.HTTPException:
        return None, "erro"


async def _buscar_mensagem(client, canal_id: int, mensagem_id: int):
    canal, estado = await _buscar_canal(client, canal_id)
    if canal is None:
        return None, estado
    try:
        return await canal.fetch_message(mensagem_id), "ok"
    except discord.NotFound:
        return None, "apagado"
    except discord.HTTPException:
        return None, "erro"


async def atualizar_mensagem_sorteio(client, g: dict, msg=None):
    """Reedita a mensagem pública do sorteio (contador do botão, estado encerrado...)."""
    if msg is None:
        msg, _ = await _buscar_mensagem(client, g["canal_id"], g["mensagem_id"])
        if msg is None:
            return
    try:
        if g["status"] == "ativo":
            await msg.edit(embed=embed_sorteio_ativo(g), view=GiveawayView(len(g["participantes"])))
        else:
            await msg.edit(
                embed=embed_sorteio_encerrado(g),
                view=GiveawayView(len(g["participantes"]), encerrado=True),
            )
    except discord.HTTPException:
        pass


async def filtrar_participantes(guild, g: dict) -> tuple:
    """Quem ainda pode ganhar (continua no servidor, não é bot, ainda tem o cargo exigido)
    e quantas entradas cada um tem agora. Retorna (lista_de_ids, {id: entradas})."""
    validos, pesos = [], {}
    req = g.get("cargo_requerido_id")
    for uid in g["participantes"]:
        member = guild.get_member(uid)
        if member is None:
            try:
                member = await guild.fetch_member(uid)
            except discord.HTTPException:
                continue  # saiu do servidor
        if member.bot:
            continue
        if req and not any(r.id == req for r in member.roles):
            continue
        validos.append(uid)
        pesos[uid] = entradas_do_membro(g, member)[0]
    return validos, pesos


async def anunciar_rodada(client, g: dict, ganhadores: list, referencia=None):
    """Posta a mensagem com os ganhadores + botão do ticket e abre o prazo de resgate."""
    canal, _ = await _buscar_canal(client, g["canal_id"])
    rodada = {
        "ganhadores": list(ganhadores),
        "aviso_msg_id": None,
        "prazo": time.time() + g["prazo_minutos"] * 60,
        "tratado": False,
    }
    g.setdefault("rodadas", []).append(rodada)
    if canal is not None:
        mencoes = " ".join(f"<@{u}>" for u in ganhadores)
        try:
            try:
                aviso = await canal.send(
                    content=mencoes, embed=embed_anuncio(g, rodada), view=ClaimView(),
                    reference=referencia, mention_author=False,
                )
            except discord.HTTPException:
                aviso = await canal.send(content=mencoes, embed=embed_anuncio(g, rodada), view=ClaimView())
            rodada["aviso_msg_id"] = aviso.id
        except discord.HTTPException as erro:
            print(f"[sorteio] não consegui anunciar os ganhadores: {erro!r}")
    save_giveaways()

    if rodada["aviso_msg_id"]:
        link = f"https://discord.com/channels/{g['guild_id']}/{g['canal_id']}/{rodada['aviso_msg_id']}"
        for uid in ganhadores:  # aviso por DM (se a pessoa deixar)
            try:
                user = await client.fetch_user(uid)
                await user.send(
                    f"🎉 Você ganhou **{g['premio']}**! Abra o ticket do prêmio em até "
                    f"{g['prazo_minutos']} minutos: {link}"
                )
            except discord.HTTPException:
                pass
    return rodada


async def finalizar_sorteio(client, guild_id: int, sid: str) -> str:
    """Encerra o sorteio, sorteia e anuncia. Retorna: ok | sem_participantes | cancelado |
    erro | inexistente | ja_encerrado."""
    g = get_giveaway(guild_id, sid)
    if not g:
        return "inexistente"
    if g["status"] != "ativo":
        return "ja_encerrado"
    g["status"] = "encerrando"  # trava: ninguém mais entra e ninguém finaliza 2x

    msg, estado = await _buscar_mensagem(client, g["canal_id"], g["mensagem_id"])
    if estado == "apagado":  # apagar a mensagem do sorteio cancela ele
        giveaways_data.get(str(guild_id), {}).pop(str(sid), None)
        save_giveaways()
        return "cancelado"
    if estado == "erro":
        g["tentativas"] = g.get("tentativas", 0) + 1
        if g["tentativas"] >= 10:
            giveaways_data.get(str(guild_id), {}).pop(str(sid), None)
            save_giveaways()
            return "cancelado"
        g["status"] = "ativo"
        g["tentar_apos"] = time.time() + 30
        save_giveaways()
        return "erro"

    guild = client.get_guild(guild_id)
    if guild is not None:
        validos, pesos = await filtrar_participantes(guild, g)
    else:
        validos, pesos = list(g["participantes"]), {}
    ganhadores = sortear(validos, g["ganhadores_qtd"], pesos=pesos)

    g["status"] = "encerrado"
    g["encerrou_em"] = time.time()
    g["ganhadores"] = list(ganhadores)
    g.setdefault("rodadas", [])
    save_giveaways()

    await atualizar_mensagem_sorteio(client, g, msg)
    if not ganhadores:
        canal, _ = await _buscar_canal(client, g["canal_id"])
        if canal is not None:
            try:
                await canal.send(f"😢 O sorteio de **{g['premio']}** terminou sem participantes válidos.")
            except discord.HTTPException:
                pass
        return "sem_participantes"
    await anunciar_rodada(client, g, ganhadores, referencia=msg)
    return "ok"


async def expirar_rodada(client, g: dict, rodada: dict):
    """Passou o prazo do ticket: marca quem perdeu e avisa o organizador."""
    rodada["tratado"] = True
    save_giveaways()
    perderam = [u for u in rodada["ganhadores"] if u not in g.get("resgatados", [])]

    if rodada.get("aviso_msg_id"):
        msg, _ = await _buscar_mensagem(client, g["canal_id"], rodada["aviso_msg_id"])
        if msg is not None:
            try:
                await msg.edit(embed=embed_anuncio(g, rodada, expirado=True), view=None)
            except discord.HTTPException:
                pass

    if perderam:
        canal, _ = await _buscar_canal(client, g["canal_id"])
        if canal is not None:
            nomes = ", ".join(f"<@{u}>" for u in perderam)
            embed = discord.Embed(
                description=(
                    f"⏰ O prazo de {g['prazo_minutos']} minutos acabou e {nomes} não abriu o ticket do prêmio "
                    f"**{g['premio']}**.\nUse `/sorteio rerolar` para sortear outro ganhador."
                ),
                color=discord.Color.red(),
            )
            try:
                await canal.send(content=f"<@{g['organizador_id']}>", embed=embed)
            except discord.HTTPException:
                pass


async def processar_sorteios(client):
    agora = time.time()
    for gid, itens in list(giveaways_data.items()):
        for sid, g in list(itens.items()):
            try:
                if g["status"] == "ativo" and agora >= max(g["termina_em"], g.get("tentar_apos", 0)):
                    await finalizar_sorteio(client, int(gid), sid)
                for rodada in g.get("rodadas", []):
                    if not rodada.get("tratado") and agora >= rodada["prazo"]:
                        await expirar_rodada(client, g, rodada)
                if (
                    g["status"] == "encerrado"
                    and all(r.get("tratado") for r in g.get("rodadas", []))
                    and agora - (g.get("encerrou_em") or agora) > SORTEIO_RETENCAO_SEGUNDOS
                ):
                    itens.pop(sid, None)
                    save_giveaways()
            except Exception as erro:  # noqa: BLE001 — um sorteio com problema não derruba os outros
                print(f"[sorteio] erro ao processar {sid}: {erro!r}")


async def loop_sorteios(client):
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            await processar_sorteios(client)
        except Exception as erro:  # noqa: BLE001
            print(f"[sorteio] erro no loop: {erro!r}")
        await asyncio.sleep(SORTEIO_TICK_SEGUNDOS)


# ---------- comandos ----------

def _opcoes_sorteio(interaction: discord.Interaction, current: str, status: str) -> list:
    out = []
    for sid, g in giveaways_data.get(str(interaction.guild_id), {}).items():
        if g["status"] != status:
            continue
        canal = interaction.guild.get_channel(g["canal_id"]) if interaction.guild else None
        nome = f"{g['premio']} — #{canal.name}" if canal else g["premio"]
        if current.lower() in nome.lower():
            out.append(app_commands.Choice(name=nome[:100], value=sid))
    return out[:25]


class SorteioGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="sorteio",
            description="Cria e gerencia sorteios",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction) or is_admin(interaction):
            return True
        raise app_commands.CheckFailure("Apenas a equipe da loja pode gerenciar sorteios.")

    @app_commands.command(name="criar", description="Cria um sorteio com botão de participar")
    @app_commands.describe(
        premio="O que está sendo sorteado",
        duracao="Quanto tempo dura. Ex: 30m, 2h, 1d ou 1h30m",
        ganhadores="Quantos ganhadores (padrão 1)",
        organizador="Quem organizou o sorteio (padrão: você)",
        canal="Canal onde o sorteio será postado (padrão: este)",
        descricao="Texto extra que aparece no sorteio (opcional)",
        cargo_requerido="Só quem tem esse cargo pode participar (opcional)",
        prazo_resgate="Minutos que o ganhador tem pra abrir o ticket (padrão 10)",
        entradas_extras="Aplicar as entradas extras por cargo (veja /entradas)",
        banner="Imagem que aparece no final do sorteio (opcional)",
    )
    async def criar(
        self,
        interaction: discord.Interaction,
        premio: app_commands.Range[str, 1, 200],
        duracao: str,
        ganhadores: app_commands.Range[int, 1, 20] = 1,
        organizador: discord.Member = None,
        canal: discord.TextChannel = None,
        descricao: app_commands.Range[str, 1, 1500] = None,
        cargo_requerido: discord.Role = None,
        prazo_resgate: app_commands.Range[int, 1, 1440] = 10,
        entradas_extras: bool = True,
        banner: discord.Attachment = None,
    ):
        segundos = parse_duracao(duracao)
        if segundos is None or not (SORTEIO_MIN_SEGUNDOS <= segundos <= SORTEIO_MAX_SEGUNDOS):
            await interaction.response.send_message(
                "⏱️ Duração inválida. Use por exemplo `30m`, `2h`, `1d` ou `1h30m` "
                "(mínimo 30 segundos, máximo 30 dias).",
                ephemeral=True,
            )
            return

        alvo = canal or interaction.channel
        org = organizador or interaction.user
        cfg = get_guild_config(interaction.guild_id)
        g = {
            "guild_id": interaction.guild_id,
            "canal_id": alvo.id,
            "mensagem_id": None,
            "premio": premio,
            "descricao": descricao,
            "banner_url": banner.url if banner else None,
            "organizador_id": org.id,
            "criador_id": interaction.user.id,
            "ganhadores_qtd": ganhadores,
            "termina_em": time.time() + segundos,
            "prazo_minutos": prazo_resgate,
            "cargo_requerido_id": cargo_requerido.id if cargo_requerido else None,
            # cópia da tabela de entradas no momento da criação — mudar /entradas depois não altera sorteios em andamento
            "entradas_extras": dict(cfg.get("sorteio_entradas") or {}) if entradas_extras else {},
            "participantes": [],
            "status": "ativo",
            "ganhadores": [],
            "rodadas": [],
            "resgatados": [],
            "tickets": {},
        }

        await interaction.response.defer(ephemeral=True)
        try:
            msg = await alvo.send(embed=embed_sorteio_ativo(g), view=GiveawayView(0))
        except discord.HTTPException:
            await interaction.followup.send(
                f"Não consegui postar o sorteio em {alvo.mention} — confira se o bot pode enviar mensagens lá.",
                ephemeral=True,
            )
            return
        g["mensagem_id"] = msg.id
        get_guild_giveaways(interaction.guild_id)[str(msg.id)] = g
        save_giveaways()
        await interaction.followup.send(
            f"🎉 Sorteio criado em {alvo.mention}! Termina <t:{int(g['termina_em'])}:R>.", ephemeral=True
        )

    @app_commands.command(name="encerrar", description="Encerra um sorteio agora e sorteia os ganhadores")
    @app_commands.describe(sorteio="Qual sorteio encerrar")
    async def encerrar(self, interaction: discord.Interaction, sorteio: str):
        g = get_giveaway(interaction.guild_id, sorteio)
        if not g or g["status"] != "ativo":
            await interaction.response.send_message("Sorteio não encontrado ou já encerrado.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        resultado = await finalizar_sorteio(interaction.client, interaction.guild_id, sorteio)
        textos = {
            "ok": "✅ Sorteio encerrado e ganhadores anunciados!",
            "sem_participantes": "Sorteio encerrado, mas ninguém válido participou.",
            "cancelado": "A mensagem do sorteio foi apagada, então ele foi cancelado.",
            "erro": "Não consegui acessar a mensagem do sorteio agora. Tente de novo em instantes.",
        }
        await interaction.followup.send(textos.get(resultado, "Esse sorteio já tinha sido encerrado."), ephemeral=True)

    @encerrar.autocomplete("sorteio")
    async def encerrar_ac(self, interaction: discord.Interaction, current: str):
        return _opcoes_sorteio(interaction, current, "ativo")

    @app_commands.command(name="rerolar", description="Sorteia outro ganhador de um sorteio já encerrado")
    @app_commands.describe(sorteio="Qual sorteio", quantidade="Quantos novos ganhadores (padrão 1)")
    async def rerolar(
        self, interaction: discord.Interaction, sorteio: str, quantidade: app_commands.Range[int, 1, 20] = 1
    ):
        g = get_giveaway(interaction.guild_id, sorteio)
        if not g or g["status"] != "encerrado":
            await interaction.response.send_message(
                "Só dá pra sortear de novo em um sorteio já encerrado. Use /sorteio encerrar antes, se ele ainda está rodando.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        # Só concorre quem já estava inscrito quando o sorteio acabou — as inscrições não reabrem.
        validos, pesos = await filtrar_participantes(interaction.guild, g)
        ja_ganharam = set(todos_ganhadores(g)) | {u for r in g.get("rodadas", []) for u in r["ganhadores"]}
        novos = sortear(validos, quantidade, excluir=ja_ganharam, pesos=pesos)
        if not novos:
            await interaction.followup.send("Não sobrou ninguém elegível pra sortear.", ephemeral=True)
            return
        g["ganhadores"] = todos_ganhadores(g) + novos
        save_giveaways()
        msg, _ = await _buscar_mensagem(interaction.client, g["canal_id"], g["mensagem_id"])
        await atualizar_mensagem_sorteio(interaction.client, g, msg)
        await anunciar_rodada(interaction.client, g, novos, referencia=msg)
        await interaction.followup.send(f"🔁 {plural_ganhadores(len(novos))} sorteado(s) e anunciado(s)!", ephemeral=True)

    @rerolar.autocomplete("sorteio")
    async def rerolar_ac(self, interaction: discord.Interaction, current: str):
        return _opcoes_sorteio(interaction, current, "encerrado")

    @app_commands.command(name="listar", description="Mostra os sorteios que estão rodando")
    async def listar(self, interaction: discord.Interaction):
        ativos = [g for g in get_guild_giveaways(interaction.guild_id).values() if g["status"] == "ativo"]
        if not ativos:
            await interaction.response.send_message("Nenhum sorteio rodando agora.", ephemeral=True)
            return
        embed = discord.Embed(title="🎉 Sorteios em andamento", color=discord.Color.gold())
        for g in ativos[:25]:
            embed.add_field(
                name=g["premio"][:250],
                value=(
                    f"<#{g['canal_id']}> • termina <t:{int(g['termina_em'])}:R>\n"
                    f"👥 {len(g['participantes'])} participantes • 🏆 {g['ganhadores_qtd']}"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EntradasGroup(app_commands.Group):
    """Cargos que valem mais de uma entrada nos sorteios."""

    def __init__(self):
        super().__init__(
            name="entradas",
            description="Cargos que valem mais entradas nos sorteios",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode configurar as entradas dos sorteios.")

    @app_commands.command(name="adicionar", description="Faz um cargo valer várias entradas nos sorteios")
    @app_commands.describe(cargo="Cargo que ganha entradas extras", vezes="Quantas entradas esse cargo vale (2 a 20)")
    async def adicionar(self, interaction: discord.Interaction, cargo: discord.Role, vezes: app_commands.Range[int, 2, 20]):
        cfg = get_guild_config(interaction.guild_id)
        cfg.setdefault("sorteio_entradas", {})[str(cargo.id)] = vezes
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)
        await interaction.response.send_message(
            f"✅ Quem tem {cargo.mention} agora vale **{vezes} entradas** nos próximos sorteios "
            "(quem não tem nenhum cargo da lista vale 1). Sorteios que já estão rodando não mudam.",
            ephemeral=True,
        )

    @app_commands.command(name="remover", description="Tira as entradas extras de um cargo")
    @app_commands.describe(cargo="Cargo que volta a valer 1 entrada")
    async def remover(self, interaction: discord.Interaction, cargo: discord.Role):
        cfg = get_guild_config(interaction.guild_id)
        tabela = cfg.setdefault("sorteio_entradas", {})
        if str(cargo.id) not in tabela:
            await interaction.response.send_message("Esse cargo não tem entradas extras.", ephemeral=True)
            return
        del tabela[str(cargo.id)]
        config_data[str(interaction.guild_id)] = cfg
        save_json(CONFIG_FILE, config_data)
        await interaction.response.send_message(f"✅ {cargo.mention} voltou a valer 1 entrada.", ephemeral=True)

    @app_commands.command(name="listar", description="Mostra quantas entradas cada cargo vale")
    async def listar(self, interaction: discord.Interaction):
        tabela = get_guild_config(interaction.guild_id).get("sorteio_entradas") or {}
        if not tabela:
            await interaction.response.send_message(
                "Nenhum cargo com entradas extras — todo mundo vale 1 entrada. Use /entradas adicionar.",
                ephemeral=True,
            )
            return
        linhas = [f"<@&{c}> → **{n}** entradas" for c, n in sorted(tabela.items(), key=lambda x: -x[1])]
        embed = discord.Embed(
            title="✨ Entradas por cargo",
            description="\n".join(linhas) + "\n\nQuem não tem nenhum desses cargos vale 1 entrada. "
            "Se a pessoa tem mais de um, vale o maior.",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ----------------------------------------------------------------------------
# Comandos de cupom
# ----------------------------------------------------------------------------

CUPOM_MAX_SEGUNDOS = 365 * 24 * 3600


class FazerGroup(app_commands.Group):
    """/fazer cupom — só o dono da loja."""

    def __init__(self):
        super().__init__(
            name="fazer",
            description="Cria coisas para a loja",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode criar cupons.")

    @app_commands.command(name="cupom", description="Cria um cupom de desconto para os tickets de venda")
    @app_commands.describe(
        nome="Nome do cupom (ex: PROMO10) — sem espaços",
        desconto="Porcentagem de desconto (1 a 100)",
        limite="Quantas pessoas podem usar o cupom",
        duracao="Quanto tempo o cupom fica ativo. Ex: 30m, 2h, 1d ou 1d12h",
        anunciar="Canal onde o cupom será anunciado pra todo mundo (opcional)",
    )
    async def cupom(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 2, 32],
        desconto: app_commands.Range[int, 1, 100],
        limite: app_commands.Range[int, 1, 100000],
        duracao: str,
        anunciar: discord.TextChannel = None,
    ):
        codigo = normalizar_cupom(nome)
        if len(codigo) < 2:
            await interaction.response.send_message(
                embed=embed_erro_cupom("Nome inválido. Use letras, números, `-` ou `_` (mínimo 2 caracteres)."),
                ephemeral=True,
            )
            return
        segundos = parse_duracao(duracao)
        if segundos is None or not (60 <= segundos <= CUPOM_MAX_SEGUNDOS):
            await interaction.response.send_message(
                embed=embed_erro_cupom(
                    "⏱️ Duração inválida. Use por exemplo `30m`, `2h`, `1d` ou `1d12h` "
                    "(mínimo 1 minuto, máximo 365 dias)."
                ),
                ephemeral=True,
            )
            return
        cupons = get_guild_coupons(interaction.guild_id)
        existente = cupons.get(codigo)
        if existente and not cupom_expirado(existente):
            await interaction.response.send_message(
                embed=embed_erro_cupom(
                    f"Já existe um cupom ativo chamado `{codigo}`. Apague com `/cupons apagar` ou escolha outro nome."
                ),
                ephemeral=True,
            )
            return

        cupons[codigo] = {
            "desconto": desconto,
            "limite": limite,
            "usos": [],
            "expira_em": int(time.time()) + segundos,
            "criado_por": interaction.user.id,
        }
        save_coupons()
        c = cupons[codigo]

        resumo = embed_cupom(codigo, c, titulo="✅ Cupom criado!")
        resumo.set_footer(text="Os compradores usam o botão 🏷️ Resgatar Cupom dentro do ticket.")

        extra = ""
        if anunciar:
            anuncio = embed_cupom(codigo, c, titulo="🎁 NOVO CUPOM DE DESCONTO!")
            anuncio.add_field(
                name="📝 Como usar",
                value="1️⃣ Abra um ticket no painel de vendas\n"
                      "2️⃣ Clique em **🏷️ Resgatar Cupom**\n"
                      f"3️⃣ Digite `{codigo}` e pronto — o preço cai na hora!",
                inline=False,
            )
            try:
                await anunciar.send(embed=anuncio)
                extra = f"\n📣 Anúncio enviado em {anunciar.mention}."
            except discord.HTTPException:
                extra = f"\n⚠️ Não consegui enviar o anúncio em {anunciar.mention} (falta permissão?)."

        await interaction.response.send_message(content=extra or None, embed=resumo, ephemeral=True)
        await send_log(
            interaction.guild_id,
            f"🏷️ Cupom **{codigo}** ({desconto}%, {limite} usos) criado por {interaction.user.mention}.",
        )


async def cupom_autocomplete(interaction: discord.Interaction, current: str) -> list:
    cupons = get_guild_coupons(interaction.guild_id)
    return [
        app_commands.Choice(name=codigo, value=codigo)
        for codigo in cupons
        if current.upper() in codigo
    ][:25]


class CuponsGroup(app_commands.Group):
    """/cupons listar | apagar — só o dono da loja."""

    def __init__(self):
        super().__init__(
            name="cupons",
            description="Gerencia os cupons de desconto",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode gerenciar cupons.")

    @app_commands.command(name="listar", description="Mostra os cupons criados e quanto cada um já foi usado")
    async def listar(self, interaction: discord.Interaction):
        cupons = get_guild_coupons(interaction.guild_id)
        if not cupons:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🏷️ Cupons",
                    description="Nenhum cupom criado ainda.\nUse `/fazer cupom` pra criar o primeiro!",
                    color=discord.Color.light_grey(),
                ),
                ephemeral=True,
            )
            return
        ativos = sum(1 for c in cupons.values() if status_cupom(c) == "🟢 Ativo")
        embed = discord.Embed(
            title="🏷️ Cupons da loja",
            description=f"**{ativos}** ativo(s) de **{len(cupons)}** no total",
            color=discord.Color.gold(),
        )
        for codigo, c in list(cupons.items())[:24]:
            usados, limite = len(c["usos"]), c["limite"]
            embed.add_field(
                name=f"{status_cupom(c)} • {codigo}",
                value=(
                    f"💸 **{c['desconto']}%** de desconto\n"
                    f"{barra_progresso(usados, limite)} **{usados}/{limite}**\n"
                    f"⏰ expira <t:{int(c['expira_em'])}:R>"
                ),
                inline=True,
            )
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="apagar", description="Apaga um cupom")
    @app_commands.describe(nome="Cupom que será apagado")
    @app_commands.autocomplete(nome=cupom_autocomplete)
    async def apagar(self, interaction: discord.Interaction, nome: str):
        codigo = normalizar_cupom(nome)
        cupons = get_guild_coupons(interaction.guild_id)
        if codigo not in cupons:
            await interaction.response.send_message(
                embed=embed_erro_cupom("Esse cupom não existe."), ephemeral=True
            )
            return
        del cupons[codigo]
        save_coupons()
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Cupom apagado",
                description=f"`{codigo}` foi removido.\nTickets que já resgataram ele mantêm o desconto.",
                color=discord.Color.orange(),
            ),
            ephemeral=True,
        )


# ----------------------------------------------------------------------------
# Registro de comandos e tratamento de erros
# ----------------------------------------------------------------------------

bot.tree.add_command(EstoqueGroup())
bot.tree.add_command(PainelGroup())
bot.tree.add_command(TicketOpcoesGroup())
bot.tree.add_command(PersonalizarGroup())
bot.tree.add_command(SorteioGroup())
bot.tree.add_command(EntradasGroup())
bot.tree.add_command(FazerGroup())
bot.tree.add_command(CuponsGroup())


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
async def on_member_join(member: discord.Member):
    """Mensagem automática de boas-vindas — recurso premium."""
    cfg = get_guild_config(member.guild.id)
    if not cfg.get("premium"):
        return
    canal_id = cfg.get("canal_boasvindas_id")
    texto = cfg.get("boasvindas_texto")
    if not canal_id or not texto:
        return
    channel = member.guild.get_channel(canal_id)
    if not channel:
        return

    cor = discord.Color(cfg["cor_embed"]) if cfg.get("cor_embed") is not None else discord.Color.blurple()
    embed = discord.Embed(description=texto, color=cor)
    if cfg.get("boasvindas_titulo"):
        embed.title = cfg["boasvindas_titulo"]
    if cfg.get("boasvindas_banner_url"):
        embed.set_image(url=cfg["boasvindas_banner_url"])

    try:
        await channel.send(content=member.mention, embed=embed)
    except discord.HTTPException:
        pass


@bot.event
async def on_ready():
    # Registra as views persistentes para os botões/menus continuarem
    # funcionando em mensagens antigas após reiniciar o bot.
    bot.add_view(TicketView())
    bot.add_view(HostView())
    bot.add_view(HelpTicketView())
    bot.add_view(PremioTicketView())
    for gid, itens in giveaways_data.items():
        for g in itens.values():
            if g["status"] == "ativo" and g.get("mensagem_id"):
                bot.add_view(GiveawayView(len(g["participantes"])), message_id=g["mensagem_id"])
            for rodada in g.get("rodadas", []):
                if not rodada.get("tratado") and rodada.get("aviso_msg_id"):
                    bot.add_view(ClaimView(), message_id=rodada["aviso_msg_id"])
    global sorteio_task
    if sorteio_task is None or sorteio_task.done():
        sorteio_task = asyncio.create_task(loop_sorteios(bot))
    migrate_legacy_products()
    for gid, panels in panels_data.items():
        for p in panels:
            bot.add_view(ProductSelectView(int(gid), str(p["message_id"])), message_id=p["message_id"])
    for gid, panels in help_panels_data.items():
        for p in panels:
            bot.add_view(HelpTicketSelectView(int(gid)), message_id=p["message_id"])
    # Atualiza todos os painéis ao ligar: cada um passa a mostrar só os produtos dele,
    # com o estoque atual, e o ✓ da última escolha some.
    for gid in list(panels_data.keys()):
        try:
            await refresh_panels(bot, int(gid))
        except Exception as erro:  # noqa: BLE001
            print(f"[on_ready] não consegui atualizar os painéis do servidor {gid}: {erro!r}")
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
