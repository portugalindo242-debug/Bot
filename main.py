import os
import re
import json
import time
import random
import io
import asyncio
from datetime import datetime, timedelta, timezone
from threading import Thread

import discord
from discord import app_commands
from discord.ext import commands

try:
    from PIL import Image, ImageDraw, ImageFont  # só pro cartão de "Compra Aprovada" nas entregas
    PIL_OK = True
except ImportError:  # sem Pillow a entrega cai de volta pro embed comum
    PIL_OK = False

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
IMAGES_DIR = os.path.join(DATA_DIR, "imagens")  # imagens dos produtos (guardadas aqui pra nunca expirarem)

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
coupons_data = load_json(COUPONS_FILE, {})  # {guild: {CODIGO: {tipo, valor, usos_max, usos}}}
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


async def send_delivery_log(guild_id: int, embed: discord.Embed, card: dict | None = None):
    """Manda a entrega no canal de entregas. Com 'card', tenta o cartão em imagem
    (Compra Aprovada + botão Comprar); se não der, manda o embed comum."""
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_entregas_id")
    if not canal_id:
        return
    channel = bot.get_channel(canal_id)
    if not channel:
        return
    if card:
        try:
            arquivo = await montar_card_compra(channel.guild, card["buyer_id"], card["carrinho"], card["valor"])
            if arquivo:
                kwargs = {"file": arquivo}
                if card.get("link"):
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(label="Comprar", emoji="🏪", url=card["link"]))
                    kwargs["view"] = view
                await channel.send(**kwargs)
                return
        except Exception as erro:  # noqa: BLE001
            print(f"[entrega] não consegui montar o cartão, mandando o embed comum: {erro!r}")
    try:
        await channel.send(embed=embed, content="🛒 Faça seu pedido também!")
    except discord.HTTPException:
        pass


async def send_log_card(guild_id: int, texto: str, card: dict):
    """Aviso de venda concluída no canal de logs, no mesmo estilo do cartão 'Compra Aprovada'.
    Se não der pra montar o cartão, manda o texto de sempre."""
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_logs_id")
    if not canal_id:
        return
    if canal_id == cfg.get("canal_entregas_id"):
        return  # logs e entregas são o mesmo canal: o cartão da entrega já aparece lá
    channel = bot.get_channel(canal_id)
    if channel is None:
        return
    try:
        arquivo = await montar_card_compra(channel.guild, card["buyer_id"], card["carrinho"], card["valor"])
        if arquivo:
            # idêntico ao da entrega: só a imagem do cartão + botão Comprar, sem texto
            kwargs = {"file": arquivo}
            if card.get("link"):
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label="Comprar", emoji="🏪", url=card["link"]))
                kwargs["view"] = view
            await channel.send(**kwargs)
            return
    except Exception as erro:  # noqa: BLE001
        print(f"[log] não consegui montar o cartão, mandando texto: {erro!r}")
    await send_log(guild_id, message=texto)


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


def record_sale(guild_id: int, product_name: str, price: float, buyer_id: int, admin_id: int, quantidade: int = 1):
    sales = get_guild_sales(guild_id)
    sales.append(
        {"produto": product_name, "preco": price, "comprador_id": buyer_id, "admin_id": admin_id, "quantidade": quantidade}
    )
    sales_data[str(guild_id)] = sales
    save_json(SALES_FILE, sales_data)


def get_guild_panels(guild_id: int) -> list:
    gid = str(guild_id)
    if gid not in panels_data:
        panels_data[gid] = []
        save_json(PANELS_FILE, panels_data)
    return panels_data[gid]


def add_panel_record(
    guild_id: int, channel_id: int, message_id: int, banner_url: str | None, titulo: str, descricao: str,
    banner_arquivo: str | None = None,
):
    panels = get_guild_panels(guild_id)
    panels.append(
        {
            "channel_id": channel_id,
            "message_id": message_id,
            "banner_url": banner_url,
            "banner_arquivo": banner_arquivo,
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
        preco_de="Preço antigo, que aparece riscado no ticket (opcional)",
        imagem="Imagem do produto que aparece no ticket (opcional — sem ela usa o banner do painel)",
    )
    async def adicionar(
        self,
        interaction: discord.Interaction,
        nome: str,
        preco: float,
        quantidade: int,
        descricao: str,
        painel: str = None,
        preco_de: float = None,
        imagem: discord.Attachment = None,
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

        imagem_arquivo = await salvar_imagem(imagem) if imagem else None
        pid = f"{panel_id}:{slugify(nome)[:60]}"
        stock[pid] = {
            "nome": nome,
            "preco": preco,
            "quantidade": quantidade,
            "descricao": descricao,
            "painel_id": panel_id,
            "preco_de": preco_de if preco_de and preco_de > 0 else None,
            "imagem_url": imagem.url if imagem else None,
            "imagem_arquivo": imagem_arquivo,
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
        preco_de="Preço antigo riscado no ticket (opcional — use 0 pra remover)",
        imagem="Nova imagem do produto no ticket (opcional)",
    )
    async def editar(
        self,
        interaction: discord.Interaction,
        nome: str,
        preco: float = None,
        quantidade: int = None,
        descricao: str = None,
        painel: str = None,
        preco_de: float = None,
        imagem: discord.Attachment = None,
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
        if preco_de is not None:
            produto["preco_de"] = preco_de if preco_de > 0 else None
        if imagem is not None:
            novo_arquivo = await salvar_imagem(imagem)
            apagar_imagem(produto.get("imagem_arquivo"))
            produto["imagem_url"] = imagem.url
            produto["imagem_arquivo"] = novo_arquivo
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
... (128 KB restante(s))
