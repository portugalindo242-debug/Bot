importar os
importar re
importar json
tempo de importação
importar aleatório
importar io
import asyncio
from datetime import datetime, timedelta, timezone
from threading import Thread

importar discord
from discord import app_commands
from discord.ext import commands

tentar:
    from PIL import Image, ImageDraw, ImageFont # só pro cartão de "Compra Aprovada" nas entregas
    PIL_OK = Verdadeiro
exceto ImportError: # sem Pillow a entrega cai de volta pro embed comum
    PIL_OK = Falso

# ----------------------------------------------------------------------------
# keep_alive embutido aqui dentro (sem depender de um arquivo separado),
# pra evitar erro de "módulo não encontrado" em hosts que só sobem um único
#arquivo. Sobe um mini servidor Flask só pra ter uma URL que responda, caso
# o host (ou um serviço tipo UptimeRobot) precisa bater nela pra manter o
# processo acordado. Se o Flask não estiver instalado, não trava o bot.
# ----------------------------------------------------------------------------
def keep_alive():
    tentar:
        from flask import Flask
    exceto ImportError:
        print("Flask não instalado — pulando o keep_alive (o bot continua normalmente).")
        retornar

    app = Flask("keep_alive")

    @app.route("/")
    def home():
        retornar "O bot está online!"

    def run():
        porta = int(os.environ.get("PORTA", 8080))
        app.run(host="0.0.0.0", port=port)

    t = Thread(alvo=executar)
    t.daemon = Verdadeiro
    t.iniciar()


# ============================================================================
# TOKEN: no Pydroid3, pode colar direto na segunda linha abaixo. Sem renderização
# (ou em qualquer lugar que vá no GitHub), configure uma variável de ambiente
# DISCORD_TOKEN no painel do serviço — NUNCA deixe o token escrito aqui se
# for subir esse código pra um repositório.
# ============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
# ============================================================================

# ----------------------------------------------------------------------------
# Persistência simples em arquivos JSON (sem necessidade de banco de dados)
# ----------------------------------------------------------------------------

DATA_DIR = "dados"
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
ARQUIVO_DE_BRINDES = os.path.join(DIRETÓRIO_DE_DADOS, "brindes.json")
CUPONS_FILE = os.path.join(DATA_DIR, "coupons.json")
IMAGES_DIR = os.path.join(DATA_DIR, "imagens") # imagens dos produtos (guardadas aqui pra nunca expirarem)

FREE_STOCK_LIMIT = 10 # quantos produtos o plano grátis permite cadastrar (premium = ilimitado)


def load_json(path, default):
    se não os.path.exists(path):
        salvar_json(caminho, padrão)
        retornar padrão
    com open(path, "r", encoding="utf-8") as f:
        retornar json.load(f)


def salvar_json(caminho, dados):
    os.makedirs(DATA_DIR, exist_ok=True)
    com open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)


config_data = load_json(CONFIG_FILE, {})
dados_de_ações = carregar_json(ARQUIVO_DE_AÇÕES, {})
dados_bilhetes = carregar_json(ARQUIVO_BILHETES, {})
# produto/comprador de cada ticket de vendas: {guild: {canal_id: {"produto": pid, "comprador": user_id}}}
dados_informacao_do_bilhete = carregar_json(ARQUIVO_INFORMAÇÕES_DO_BILHETE, {})
help_tickets_data = load_json(HELP_TICKETS_FILE, {})
dados_painéis = carregar_json(arquivo_painéis, {})
help_panels_data = load_json(HELP_PANELS_FILE, {})
help_options_data = load_json(HELP_OPTIONS_FILE, {})
dados_vendas = carregar_json(ARQUIVO_VENDAS, {})
# sorteios: {guild: {id_da_mensagem: {...}}}
dados_sorteios = carregar_json(ARQUIVO_SORTEIOS, {})
cupons_data = load_json(COUPONS_FILE, {}) # {guild: {CODIGO: {tipo, valor, usos_max, usos}}}
keys_data = load_json(KEYS_FILE, {}) # global (não é por servidor): {key: {"used": bool, "guild_id": int|None}}


def get_guild_config(guild_id: int) -> dict:
    gid = str(guild_id)
    padrões = {
        "pix": Nenhuma,
        "cargo_dono_id": Nenhum,
        "cargo_administrador_id": Nenhum,
        "cargo_vendedor_id": Nenhum,
        "cargo_responsavel_id": Nenhum,
        "cargo_b_id": Nenhum,
        "canal_logs_id": Nenhum,
        "canal_avaliacoes_id": Nenhum,
        "canal_entregas_id": Nenhum,
        "ticket_category_id": Nenhum,
        "ticket_ajuda_category_id": Nenhum,
        "premium": Falso,
        "cor_embed": Nenhum,
        "canal_boasvindas_id": Nenhum,
        "boasvindas_titulo": Nenhum,
        "boasvindas_texto": Nenhum,
        "boasvindas_banner_url": Nenhum,
        "sorteio_entradas": {}, # {id_do_cargo: quantas entradas ele vale nos sorteios}
    }
    Se gid não estiver em config_data:
        # migra o campo antigo "admin_role_id" (versões anteriores do bot), se existir
        config_data[gid] = dict(defaults)
        salvar_json(CONFIG_FILE, config_data)
    outro:
        cfg = config_data[gid]
        alterado = Falso
        Se "cargo_vendedor_id" não estiver em cfg e cfg.get("admin_role_id"):
            cfg["cargo_vendedor_id"] = cfg["admin_role_id"]
            alterado = Verdadeiro
        para chave, valor em defaults.items():
            Se a chave não estiver no arquivo de configuração:
                cfg[chave] = valor
                alterado = Verdadeiro
        se alterado:
            salvar_json(CONFIG_FILE, config_data)
    retornar config_data[gid]


def get_staff_roles(guild: discord.Guild, cfg: dict) -> list:
    """Cargas com acesso aos tickets de VENDAS: dono, administrador e vendedor."""
    funções = []
    para digitar ("cargo_dono_id", "cargo_administrador_id", "cargo_vendedor_id"):
        rid = cfg.get(key)
        se livrar:
            função = guilda.get_role(rid)
            se função:
                funções.adicionar(função)
    retornar funções


def get_help_staff_roles(guild: discord.Guild, cfg: dict) -> list:
    """Cargas com acesso aos tickets de AJUDA: dono, administrador e responsável por ticket."""
    funções = []
    para digitar ("cargo_dono_id", "cargo_administrador_id", "cargo_responsavel_id"):
        rid = cfg.get(key)
        se livrar:
            função = guilda.get_role(rid)
            se função:
                funções.adicionar(função)
    retornar funções


# IDs de usuário com acesso de dono garantido, não importa o que aconteça
# com cargas/permissões do servidor. Adicione mais IDs separados por vírgula.
OWNER_USER_IDS = {1530756434898194438}


def is_owner(interaction: discord.Interaction) -> bool:
    """Dono da loja: quem está em OWNER_USER_IDS, tem permissão real de
    Administrador no servidor, ou a carga definida como 'Carga dona' em
    /configurar. Tem acesso total (estoque, painel, configurações e saldo)."""
    se interaction.user.id estiver em OWNER_USER_IDS:
        retornar Verdadeiro
    se interaction.user.guild_permissions.administrator:
        retornar Verdadeiro
    cfg = get_guild_config(interaction.guild_id)
    dono_id = cfg.get("cargo_dono_id")
    retornar bool(dono_id e any(r.id == dono_id para r em interaction.user.roles))


def require_owner():
    """Decorador de comandos que só o dono da loja pode usar."""
    async def predicate(interaction: discord.Interaction) -> bool:
        se is_owner(interaction):
            retornar Verdadeiro
        raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")
    retornar app_commands.check(predicado)


def require_premium():
    """Decorator pra comandos que só funcionam com uma chave premium resgatada
    (e só pro dono da loja usar, igual require_owner)."""
    async def predicate(interaction: discord.Interaction) -> bool:
        se interaction.user.id estiver em OWNER_USER_IDS:
            return True # você (desenvolvedor do bot) sempre tem acesso, pra testar
        se não is_owner(interaction):
            raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")
        cfg = get_guild_config(interaction.guild_id)
        se não cfg.get("premium"):
            raise app_commands.CheckFailure(
                "🔒 Este é um recurso premium. Resgate uma chave em /configurar para desbloquear."
            )
        retornar Verdadeiro
    retornar app_commands.check(predicado)


def generate_key() -> str:
    importar segredos
    raw = secrets.token_hex(8).upper() # 16 caracteres hexadecimais
    retornar "-".join(raw[i : i + 4] para i em range(0, len(raw), 4))


async def send_log(guild_id: int, message: str = None, embed: discord.Embed = None):
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_logs_id")
    se não for canal_id:
        retornar
    canal = bot.get_channel(canal_id)
    se o canal:
        tentar:
            aguardar canal.send(content=mensagem, embed=embed)
        exceto discord.HTTPException:
            passar


async def send_delivery_log(guild_id: int, embed: discord.Embed, card: dict | None = None):
    """Manda a entrega no canal de entregas. Com 'card', tente o cartão em imagem
    (Compra Aprovada + botão Comprar); se não der, manda o embed comum."""
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_entregas_id")
    se não for canal_id:
        retornar
    canal = bot.get_channel(canal_id)
    se não for canal:
        retornar
    se for cartão:
        tentar:
            arquivo = await montar_card_compra(channel.guild, card["buyer_id"], card["carrinho"], card["valor"])
            se arquivo:
                kwargs = {"file": arquivo}
                se card.get("link"):
                    visualização = discord.ui.View()
                    view.add_item(discord.ui.Button(label="Comprar", emoji="🏪", url=card["link"]))
                    kwargs["view"] = view
                aguardar canal.send(**kwargs)
                retornar
        exceto Exceção como erro: # noqa: BLE001
            print(f"[entrega] não consegui montar o cartão, mandando o embed comum: {erro!r}")
    tentar:
        await channel.send(embed=embed, content="🛒 Faça seu pedido também!")
    exceto discord.HTTPException:
        passar


async def send_log_card(guild_id: int, texto: str, card: dict):
    """Aviso de venda concluída no canal de toras, no mesmo estilo do cartão 'Compra Aprovada'.
    Se não der pra montar o cartão, manda o texto de sempre."""
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_logs_id")
    se não for canal_id:
        retornar
    se canal_id == cfg.get("canal_entregas_id"):
        return # logs e entregas são o mesmo canal: o cartão da entrega já aparece lá
    canal = bot.get_channel(canal_id)
    Se o canal for None:
        retornar
    tentar:
        arquivo = await montar_card_compra(channel.guild, card["buyer_id"], card["carrinho"], card["valor"])
        se arquivo:
            # idêntico ao da entrega: só a imagem do cartão + botão Comprar, sem texto
            kwargs = {"file": arquivo}
            se card.get("link"):
                visualização = discord.ui.View()
                view.add_item(discord.ui.Button(label="Comprar", emoji="🏪", url=card["link"]))
                kwargs["view"] = view
            aguardar canal.send(**kwargs)
            retornar
    exceto Exceção como erro: # noqa: BLE001
        print(f"[log] não consegui montar o cartão, mandando texto: {erro!r}")
    aguardar send_log(guild_id, mensagem=texto)


async def send_review_public(guild_id: int, message: str):
    cfg = get_guild_config(guild_id)
    canal_id = cfg.get("canal_avaliacoes_id")
    se não for canal_id:
        retornar
    canal = bot.get_channel(canal_id)
    se o canal:
        tentar:
            aguardar canal.enviar(mensagem)
        exceto discord.HTTPException:
            passar


def get_guild_stock(guild_id: int) -> dict:
    gid = str(guild_id)
    se gid não estiver em stock_data:
        stock_data[gid] = {}
        salvar_json(ARQUIVO_DE_AÇÕES, dados_de_ações)
    retornar stock_data[gid]


def get_guild_sales(guild_id: int) -> lista:
    gid = str(guild_id)
    se gid não estiver em sales_data:
        dados_vendas[gid] = []
        salvar_json(ARQUIVO_DE_VENDAS, dados_de_vendas)
    retornar dados_de_vendas[gid]


def record_sale(guild_id: int, product_name: str, price: float, buyer_id: int, admin_id: int, quantidade: int = 1):
    vendas = obter_vendas_da_guilda(id_da_guilda)
    vendas.adicionar(
        {"produto": product_name, "preco": preço, "comprador_id": buyer_id, "admin_id": admin_id, "quantidade": quantidade}
    )
    dados_vendas[str(id_guilda)] = vendas
    salvar_json(ARQUIVO_DE_VENDAS, dados_de_vendas)


def get_guild_panels(guild_id: int) -> lista:
    gid = str(guild_id)
    se gid não estiver em panels_data:
        dados_painéis[gid] = []
        salvar_json(arquivo_de_painéis, dados_dos_painéis)
    retornar dados_painéis[gid]


def adicionar_registro_do_painel(
    guild_id: int, channel_id: int, message_id: int, banner_url: str | None, titulo: str, descricao: str,
    banner_arquivo:str | Nenhum = Nenhum,
):
    painéis = obter_painéis_da_guilda(id_da_guilda)
    painéis.adicionar(
        {
            "channel_id": channel_id,
            "message_id": message_id,
            "banner_url": banner_url,
            "banner_arquivo": banner_arquivo,
            "título": título,
            "descricao": descricao,
        }
    )
    dados_painéis[str(id_guilda)] = painéis
    salvar_json(arquivo_de_painéis, dados_dos_painéis)


async def _fetch_panel_message(client: discord.Client, p: dict):
    """Busca a mensagem de um painel. Retorna (mensagem, descartar).
    descartar=True só quando o canal/mensagem foi realmente desligado;
    erro passageiro (rede, limite de tarifa) NÃO descartar o registro."""
    canal = cliente.get_channel(p["channel_id"])
    Se o canal for None:
        tentar:
            canal = aguarde cliente.buscar_canal(p["canal_id"])
        exceto discord.NotFound:
            Retorna None, True
        exceto discord.HTTPException:
            Retorna None, False
    tentar:
        return await channel.fetch_message(p["message_id"]), False
    exceto discord.NotFound:
        Retorna None, True
    exceto discord.HTTPException:
        Retorna None, False


async def refresh_panels(client: discord.Client, guild_id: int):
    """Atualiza o menu de produtos de cada painel de vendas, mostrando apenas os
    produtos DAQUELE painel e o estoque atual. Também zero ou ✓ da última escolha."""
    gid = str(guild_id)
    ainda_válido = []
    para p em panels_data.get(gid, []):
        mensagem, descartar = await _fetch_panel_message(cliente, p)
        se:
            continuar
        Se a mensagem não for None:
            tentar:
                # Só troca o menu — o embed (banner/título/descrição) fica igual.
                await message.edit(view=ProductSelectView(guild_id, str(p["message_id"])))
            exceto discord.NotFound:
                continuar
            exceto discord.HTTPException:
                passar
        ainda_válido.append(p)
    dados_painéis[gid] = ainda_válido
    salvar_json(arquivo_de_painéis, dados_dos_painéis)


def list_sales_panels(guild_id: int) -> list:
    retornar lista(painéis_dados.get(str(id_guilda), []))


def panel_label(guild: discord.Guild | None, p: dict) -> str:
    canal = guild.get_channel(p["channel_id"]) se guild senão None
    nome_canal = f"#{canal.name}" if canal else "canal desligado"
    titulo = p.get("titulo") ou f"Painel {p['message_id']}"
    retornar f"{nome_canal} — {titulo}"[:100]


def resolve_panel_id(guild_id: int, painel: str | None) -> tuple[str | None, str | None]:
    """Descobre em qual painel o comando de estoque deve mexer. Retorna (painel_id, erro)."""
    painéis = listar_painéis_de_vendas(id_da_guilda)
    ids = {str(p["message_id"]) para p em painéis}
    se painel:
        se painel em ids:
            retornar painel, Nenhum
        return None, "Painel não encontrado — escolha um da lista que aparece no campo **painel**."
    se não houver painéis:
        return None, "Você ainda não tem nenhum painel de vendas. Crie um com /painel vendas primeiro."
    se len(painéis) == 1:
        retornar str(panels[0]["message_id"]), None
    return None, "Você tem mais de um painel de vendas — escolha qual no campo **painel**."


def find_product(stock: dict, panel_id: str, nome: str):
    alvo = slugify(nome)
    para pid, p em stock.items():
        se p.get("painel_id") == panel_id e slugify(p["nome"]) == alvo:
            retornar pid, p
    retorna Nenhum, Nenhum


def migrate_legacy_products():
    """Produtos criados antes dos painéis possuem estoque próprio não possuem 'painel_id'.
    Eles passam a pertencer ao primeiro painel do servidor (os novos painéis apresentam vazios)."""
    alterado = Falso
    para gid, estoque em stock_data.items():
        painéis = dados_painéis.get(gid, [])
        se não houver painéis:
            continuar
        padrao = str(panels[0]["message_id"])
        para p em stock.values():
            se "painel_id" não estiver em p:
                p["painel_id"] = padrao
                alterado = Verdadeiro
    se alterado:
        salvar_json(ARQUIVO_DE_AÇÕES, dados_de_ações)


async def painel_autocomplete(interaction: discord.Interaction, current: str) -> list:
    saída = []
    para p em list_sales_panels(interaction.guild_id):
        rótulo = rótulo_do_painel(interação.guilda, p)
        se current.lower() estiver em label.lower():
            out.append(app_commands.Choice(name=label, value=str(p["message_id"])))
    retornar saída[:25]


async def produto_autocomplete(interaction: discord.Interaction, current: str) -> list:
    painel = getattr(interaction.namespace, "painel", None)
    panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
    se erro:
        retornar []
    saída = []
    para p em get_guild_stock(interaction.guild_id).values():
        se p.get("painel_id") == panel_id e current.lower() em p["nome"].lower():
            out.append(app_commands.Choice(name=p["nome"][:100], value=p["nome"][:100]))
    retornar saída[:25]


def get_guild_help_options(guild_id: int) -> dict:
    gid = str(guild_id)
    se gid não estiver em help_options_data:
        help_options_data[gid] = {}
        salvar_json(ARQUIVO_DE_OPÇÕES_DE_AJUDA, dados_de_opções_de_ajuda)
    retornar help_options_data[gid]


def get_guild_help_panels(guild_id: int) -> list:
    gid = str(guild_id)
    se gid não estiver em help_panels_data:
        help_panels_data[gid] = []
        salvar_json(ARQUIVO_PAINÉIS_DE_AJUDA, dados_painéis_de_ajuda)
    retornar help_panels_data[gid]


def adicionar_registro_painel_de_ajuda(
    guild_id: int, channel_id: int, message_id: int, banner_url: str | None, titulo: str, descricao: str
):
    painéis = obter_painéis_de_ajuda_da_guilda(id_da_guilda)
    painéis.adicionar(
        {
            "channel_id": channel_id,
            "message_id": message_id,
            "banner_url": banner_url,
            "título": título,
            "descricao": descricao,
        }
    )
    help_panels_data[str(guild_id)] ​​= painéis
    salvar_json(ARQUIVO_PAINÉIS_DE_AJUDA, dados_painéis_de_ajuda)


async def refresh_help_panels(client: discord.Client, guild_id: int):
    """Atualiza o menu de tipos de atendimento de todos os painéis de ticket
    já publicado (e zero ou ✓ da última escolha)."""
    gid = str(guild_id)
    ainda_válido = []
    para p em help_panels_data.get(gid, []):
        mensagem, descartar = await _fetch_panel_message(cliente, p)
        se:
            continuar
        Se a mensagem não for None:
            tentar:
                aguardar mensagem.edit(view=HelpTicketSelectView(guild_id))
            exceto discord.NotFound:
                continuar
            exceto discord.HTTPException:
                passar
        ainda_válido.append(p)
    help_panels_data[gid] = ainda_válido
    salvar_json(ARQUIVO_PAINÉIS_DE_AJUDA, dados_painéis_de_ajuda)


def slugify(nome:str) ->str:
    return nome.strip().lower().replace(" ", "_")


# ----------------------------------------------------------------------------
# Robô
# ----------------------------------------------------------------------------

intents = discord.Intents.default()
intents.members = True # necessário para evento de boas-vindas (recurso premium)
bot = commands.Bot(command_prefix="!", intents=intents)


# ----------------------------------------------------------------------------
# /configurar — painel de configuração da loja (PIX, cargas e canais)
# ----------------------------------------------------------------------------

class PixModal(discord.ui.Modal, title="Configurar chave PIX"):
    pix = discord.ui.TextInput(
        rótulo="Chave PIX",
        placeholder="CPF, e-mail, telefone ou chave solicitada",
        obrigatório=Verdadeiro,
        comprimento_máximo=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        cfg["pix"] = self.pix.value.strip()
        config_data[str(interaction.guild_id)] ​​= cfg
        salvar_json(CONFIG_FILE, config_data)
        aguardar interação.resposta.enviar_mensagem("Chave PIX salva ✅", ephemeral=True)


classe SingleRoleSelect(discord.ui.RoleSelect):
    def __init__(self, field: str, label: str):
        super().__init__(placeholder=f"Seleção: {label}")
        self.campo = campo
        self.field_label = label

    async def callback(self, interaction: discord.Interaction):
        papel = self.valores[0]
        cfg = get_guild_config(interaction.guild_id)
        cfg[self.field] = role.id
        config_data[str(interaction.guild_id)] ​​= cfg
        salvar_json(CONFIG_FILE, config_data)
        aguardar interação.resposta.edit_message(content=f"{self.field_label} definido como {role.mention} ✅", view=None)


classe SingleRoleSelectView(discord.ui.View):
    def __init__(self, field: str, label: str):
        super().__init__(timeout=60)
        self.add_item(SingleRoleSelect(campo, rótulo))


classe SingleChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, field: str, label: str):
        super().__init__(placeholder=f"Selecione: {label}", channel_types=[discord.ChannelType.text])
        self.campo = campo
        self.field_label = label

    async def callback(self, interaction: discord.Interaction):
        canal = self.valores[0]
        cfg = get_guild_config(interaction.guild_id)
        cfg[self.field] = channel.id
        config_data[str(interaction.guild_id)] ​​= cfg
        salvar_json(CONFIG_FILE, config_data)
        aguardar interação.resposta.editar_mensagem(
            content=f"{self.field_label} definido como {channel.mention} ✅", view=None
        )


classe SingleChannelSelectView(discord.ui.View):
    def __init__(self, field: str, label: str):
        super().__init__(timeout=60)
        self.add_item(SingleChannelSelect(campo, rótulo))


def build_config_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    def role_str(rid):
        role = guild.get_role(rid) se rid senão None
        retornar role.mention se role else "não definido"

    def chan_str(cid):
        ch = guild.get_channel(cid) se cid senão None
        return ch.mention if ch else "não definido"

    embed = discord.Embed(title="⚙️ Configuração da loja", color=discord.Color.blurple())
    embed.add_field(name="Pix vendedor", value="configurado ✅" if cfg.get("pix") else "não configurado", inline=False)
    embed.add_field(name="Cargo dono (acesso a tudo)", value=role_str(cfg.get("cargo_dono_id")), inline=False)
    incorporar.adicionar_campo(
        name="Administrador de carga (vendas + ajuda)", value=role_str(cfg.get("cargo_administrador_id")), inline=False
    )
    embed.add_field(name="Carga vendedor (só vendas)", value=role_str(cfg.get("cargo_vendedor_id")), inline=False)
    incorporar.adicionar_campo(
        name="Responsável por ticket (só ajuda)", value=role_str(cfg.get("cargo_responsavel_id")), inline=False
    )
    embed.add_field(name="Cargo membro", value=role_str(cfg.get("cargo_membro_id")), inline=False)
    embed.add_field(name="Canal de logs", value=chan_str(cfg.get("canal_logs_id")), inline=False)
    embed.add_field(name="Canal de avaliações", value=chan_str(cfg.get("canal_avaliacoes_id")), inline=False)
    embed.add_field(name="Canal de entregas", value=chan_str(cfg.get("canal_entregas_id")), inline=False)

    premium = cfg.get("premium", False)
    incorporar.adicionar_campo(
        nome="Chave",
        value="✅ ativos — recursos premium liberados" if premium else "nenhuma (recursos de nome/foto/cor bloqueados)",
        inline=False,
    )
    Se for premium:
        embed.add_field(name="Canal de boas-vindas", value=chan_str(cfg.get("canal_boasvindas_id")), inline=False)
    outro:
        incorporar.adicionar_campo(
            name="Limite do estoque (plano grátis)", value=f"{FREE_STOCK_LIMIT} produtos", inline=False
        )
    retornar incorporado


classe KeyModal(discord.ui.Modal, title="Resgatar Key Premium"):
    chave = discord.ui.TextInput(label="Chave", placeholder="XXXX-XXXX-XXXX-XXXX", max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        k = self.key.value.strip().upper()
        info = keys_data.get(k)
        se não houver informação:
            await interaction.response.send_message("❌ Key inválida.", ephemeral=True)
            retornar
        se info.get("usado"):
            await Interaction.response.send_message("❌ Essa chave já foi usada em outro servidor.", ephemeral=True)
            retornar

        info["usado"] = Verdadeiro
        info["guild_id"] = interação.guild_id
        dados_chaves[k] = informações
        salvar_json(ARQUIVO_DE_CHAVES, dados_das_chaves)

        cfg = get_guild_config(interaction.guild_id)
        cfg["premium"] = Verdadeiro
        config_data[str(interaction.guild_id)] ​​= cfg
        salvar_json(CONFIG_FILE, config_data)

        aguardar interação.resposta.enviar_mensagem(
            "✅ Key resgatada! Recursos premium liberados pra este servidor — confira com /personalizar.",
            efêmero=Verdadeiro,
        )


classe ConfigPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="💰 Vendedor de Pix", style=discord.ButtonStyle.blurple, custom_id="cfg_pix", row=0)
    async def pix_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_modal(PixModal())

    @discord.ui.button(label="👑 Carga doada", style=discord.ButtonStyle.gray, custom_id="cfg_dono", row=0)
    async def dono_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleRoleSelectView("cargo_dono_id", "Cargo dono"), ephemeral=True
        )

    @discord.ui.button(label="🛡️ Cargo administrador", style=discord.ButtonStyle.gray, custom_id="cfg_admin", row=0)
    async def admin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleRoleSelectView("cargo_administrador_id", "Administrador de carga"), ephemeral=True
        )

    @discord.ui.button(label="🛒 Cargo vendedor", style=discord.ButtonStyle.gray, custom_id="cfg_vendedor", row=1)
    async def vendedor_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleRoleSelectView("cargo_vendedor_id", "Carga vendedor"), efêmero=True
        )

    @discord.ui.button(label="📞 Responsável por ticket", style=discord.ButtonStyle.gray, custom_id="cfg_responsavel", row=1)
    async def responsavel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleRoleSelectView("cargo_responsavel_id", "Responsável por ticket"), ephemeral=True
        )

    @discord.ui.button(label="👤 Carregar membro", style=discord.ButtonStyle.gray, custom_id="cfg_membro", row=1)
    async def membro_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleRoleSelectView("cargo_membro_id", "Cargo membro"), ephemeral=True
        )

    @discord.ui.button(label="📜 Canal de logs", style=discord.ButtonStyle.gray, custom_id="cfg_logs", row=2)
    async def logs_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleChannelSelectView("canal_logs_id", "Canal de logs"), ephemeral=True
        )

    @discord.ui.button(label="⭐ Canal de avaliações", style=discord.ButtonStyle.gray, custom_id="cfg_avaliacoes", row=2)
    async def avaliacoes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleChannelSelectView("canal_avaliacoes_id", "Canal de avaliações"), efêmero=True
        )

    @discord.ui.button(label="📦 Canal de entregas", style=discord.ButtonStyle.gray, custom_id="cfg_entregas", row=3)
    async def entregas_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_mensagem(
            view=SingleChannelSelectView("canal_entregas_id", "Canal de entregas"), ephemeral=True
        )

    @discord.ui.button(label="🔑 Salvar chave", style=discord.ButtonStyle.green, custom_id="cfg_key", row=3)
    async def key_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguardar interação.resposta.enviar_modal(KeyModal())

    @discord.ui.button(label="👋 Canal de boas-vindas", style=discord.ButtonStyle.gray, custom_id="cfg_boasvindas", row=4)
    async def boasvindas_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild_id)
        se não cfg.get("premium") e interaction.user.id não estiver em OWNER_USER_IDS:
            aguardar interação.resposta.enviar_mensagem(
                "🔒 Recurso premium — resgatar uma chave primeiro (botão 🔑 acima).", ephemeral=True
            )
            retornar
        aguardar interação.resposta.enviar_mensagem(
            view=SingleChannelSelectView("canal_boasvindas_id", "Canal de boas-vindas"), efêmero=True
        )


@bot.tree.command(name="configurar", description="Configurar o PIX, cargas e canais da loja")
@app_commands.default_permissions(administrator=True)
@require_owner()
async def configurar(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    embed = build_config_embed(interaction.guild, cfg)
    aguardar interação.resposta.enviar_mensagem(embed=embed, view=ConfigPanelView(), ephemeral=True)


@bot.tree.command(name="gerarkey", description="[Só o dono do bot] Gera uma nova key premium pra vender")
async def gerarkey(interaction: discord.Interaction):
    Se interaction.user.id não estiver em OWNER_USER_IDS:
        aguarde interação.response.send_message("Só o dono do bot pode gerar chaves.", ephemeral=True)
        retornar
    chave = gerar_chave()
    enquanto a chave estiver em keys_data:
        chave = gerar_chave()
    keys_data[key] = {"used": False, "guild_id": None}
    salvar_json(ARQUIVO_DE_CHAVES, dados_das_chaves)
    aguardar interação.resposta.enviar_mensagem(f"🔑 Chave Nova gerada:\n```{chave}```", efêmero=True)


@bot.tree.command(name="listarkeys", description="[Só o dono do bot] Lista as chaves geradas e o status delas")
async def listarkeys(interaction: discord.Interaction):
    Se interaction.user.id não estiver em OWNER_USER_IDS:
        await interação.response.send_message("Só o dono do bot pode ver isso.", ephemeral=True)
        retornar
    se não houver dados_chave:
        await interação.response.send_message("Nenhuma key gerada ainda.", ephemeral=True)
        retornar
    nao_usadas = [k para k, v em keys_data.items() se não v.get("usado")]
    usadas = [(k, v.get("guild_id")) for k, v in keys_data.items() if v.get("used")]
    embed = discord.Embed(title="🔑 Chaves geradas", color=discord.Color.gold())
    incorporar.adicionar_campo(
        name=f"Disponíveis ({len(nao_usadas)})", value="\n".join(f"`{k}`" for k in nao_usadas[:15]) ou "nenhuma",
        inline=False,
    )
    incorporar.adicionar_campo(
        name=f"Já usado ({len(usadas)})",
        valor="\n".join(f"`{k}` — servidor {gid}" para k, gid em usados[:15]) ou "nenhuma",
        inline=False,
    )
    aguardar interação.resposta.enviar_mensagem(incorporado=incorporado, efêmero=verdadeiro)


@bot.tree.command(name="debugperm", description="[Diagnóstico] Mostra suas permissões e cargas vistos pelo bot")
async def debugperm(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild_id)
    roles_str = "\n".join(f"- {r.name} (ID: {r.id})" for r in interaction.user.roles if r.name != "@everyone") or "nenhum cargo"
    embed = discord.Embed(title="🔍 Diagnóstico de permissões", color=discord.Color.orange())
    incorporar.adicionar_campo(
        name="Administrador (permissão real do Discord)",
        valor="✅ Sim" se interaction.user.guild_permissions.administrator senão "❌ Não",
        inline=False,
    )
    embed.add_field(name="Seus cargos", value=roles_str, inline=False)
    embed.add_field(name="Cargo dono configurado", value=str(cfg.get("cargo_dono_id")), inline=True)
    embed.add_field(name="Cargo administrador configurado", value=str(cfg.get("cargo_administrador_id")), inline=True)
    incorporar.adicionar_campo(
        name="Seu ID está na lista fixa de donos?",
        valor=f"✅ Sim ({interaction.user.id})" se interaction.user.id em OWNER_USER_IDS senão f"❌ Não ({interaction.user.id})",
        inline=False,
    )
    embed.add_field(name="is_owner() resultado", value="✅ Libera" if is_owner(interaction) else "❌ Bloqueia", inline=False)
    aguardar interação.resposta.enviar_mensagem(incorporado=incorporado, efêmero=verdadeiro)


@bot.tree.command(name="saldo", description="Mostra o total vendido no servidor (só tickets concluídos)")
@app_commands.default_permissions(administrator=True)
@require_owner()
async def saldo(interaction: discord.Interaction):
    vendas = obter_vendas_da_guilda(interação.id_da_guilda)
    total = soma(s["preco"] para s em vendas)
    embed = discord.Embed(title="💰 Saldo do servidor", color=discord.Color.green())
    embed.add_field(name="Total vendido", value=f"R$ {total:.2f}", inline=True)
    embed.add_field(name="Vendas concluídas", value=str(len(sales)), inline=True)
    aguardar interação.resposta.enviar_mensagem(incorporado=incorporado, efêmero=verdadeiro)


# ----------------------------------------------------------------------------
# /estoque — gerenciamento de produtos
# ----------------------------------------------------------------------------

classe ResetEstoqueView(discord.ui.View):
    """Confirmação do /estoque resetar — apagar produtos não dá pra desfazer."""

    def __init__(self, user_id: int, guild_id: int, panel_id: str | None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild_id = guild_id
        self.panel_id = panel_id # None = todos os painéis

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        Se interaction.user.id != self.user_id:
            aguarde interação.response.send_message("Só quem pediu o reset pode confirmar.", ephemeral=True)
            retornar Falso
        retornar Verdadeiro

    @discord.ui.button(label="Sim, apagando tudo", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        estoque = obter_estoque_da_guilda(self.id_da_guilda)
        Se self.panel_id for None:
            apagados = len(stock)
            estoque.limpar()
        outro:
            ids = [pid para pid, p em stock.items() se p.get("painel_id") == self.panel_id]
            apagados = len(ids)
            para pid em ids:
                del estoque[pid]
        salvar_json(ARQUIVO_DE_AÇÕES, dados_de_ações)
        aguarde interação.response.edit_message(content=f"🗑️ Pronto! {apagados} produto(s) desligado(s) do estoque.", view=None)
        aguardar atualização_painéis(interação.cliente, self.guild_id)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        aguarde interação.response.edit_message(content="Cancelado — nada foi apagado.", view=None)


MAX_PRODUTOS_POR_PAINEL = 25 # limite do Discord: um menu de seleção aceita no máximo 25 opções


classe EstoqueGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            nome="estoque",
            description="Gerenciamento do estoque de produtos de cada painel de vendas",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        se is_owner(interaction):
            retornar Verdadeiro
        raise app_commands.CheckFailure("Apenas o dono da loja pode gerenciar o estoque.")

    @app_commands.command(name="adicionar", description="Adicionar um novo produto a um painel de vendas")
    @app_commands.describe(
        nome="Nome do produto",
        preco="Preço em reais (ex: 19,90)",
        quantidade="Quantidade disponível em estoque",
        descricao="Descrição do produto",
        painel="Em qual painel de vendas esse produto vai aparecer",
        preco_de="Preço antigo, que aparece riscado no ticket (opcional)",
        imagem="Imagem do produto que aparece no ticket (opcional — sem ela usa o banner do painel)",
    )
    async def adicionar(
        auto,
        interação: discord.Interação,
        nome: str,
        preço: flutuar,
        quantidade: int,
        descrição: str,
        painel: str = Nenhum,
        preco_de: float = None,
        imagem: discord.Attachment = None,
    ):
        panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
        se erro:
            aguardar interação.resposta.enviar_mensagem(erro, efêmero=True)
            retornar

        estoque = obter_estoque_da_guilda(interação.id_da_guilda)
        se find_product(stock, panel_id, nome)[0]:
            aguardar interação.resposta.enviar_mensagem(
                "Já existe um produto com esse nome nesse painel. Use /estoque editar.", ephemeral=True
            )
            retornar

        cfg = get_guild_config(interaction.guild_id)
        se não cfg.get("premium") e len(stock) >= FREE_STOCK_LIMIT:
            aguardar interação.resposta.enviar_mensagem(
                f"🔒 O plano grátis permite até {FREE_STOCK_LIMIT} produtos. "
                "Resgate uma key premium em /configure pra cadastrar produtos ilimitados.",
                efêmero=Verdadeiro,
            )
            retornar

        no_painel = sum(1 for p in stock.values() if p.get("painel_id") == panel_id)
        se não_painel >= MAX_PRODUTOS_POR_PAINEL:
            aguardar interação.resposta.enviar_mensagem(
                f"Esse painel já tem {MAX_PRODUTOS_POR_PAINEL} produtos, que é o máximo que o Discord "
                "permite num menu. Crie outro painel com /painel vendas pra continuar.",
                efêmero=Verdadeiro,
            )
            retornar

        imagem_arquivo = aguarda salvar_imagem(imagem) if imagem else Nenhum
        pid = f"{panel_id}:{slugify(nome)[:60]}"
        estoque[pid] = {
            "nome": nome,
            "preco": preco,
            "quantidade": quantidade,
            "descricao": descricao,
            "painel_id": id_do_painel,
            "preco_de": preco_de se preco_de e preco_de > 0 senão None,
            "imagem_url": imagem.url if imagem else Nenhum,
            "imagem_arquivo": imagem_arquivo,
        }
        salvar_json(ARQUIVO_DE_AÇÕES, dados_de_ações)
        aguardar interação.resposta.defer(efêmero=True)
        aguardar atualização_painéis(interação.cliente, interação.id_guilda)
        await Interaction.followup.send(f"Produto **{nome}** adicionado com sucesso ✅", ephemeral=True)

    @adicionar.autocomplete("painel")
    async def adicionar_painel_ac(self, interaction: discord.Interaction, current: str):
        retornar aguardar painel_autocomplete(interação, atual)

    @app_commands.command(name="remover", description="Remover um produto de um painel de vendas")
    @app_commands.describe(nome="Nome do produto", painel="De qual painel de vendas remove")
    async def remover(self, interaction: discord.Interaction, nome: str, painel: str = None):
        panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
        se erro:
            aguardar interação.resposta.enviar_mensagem(erro, efêmero=True)
            retornar
        estoque = obter_estoque_da_guilda(interação.id_da_guilda)
        pid, _ = find_product(stock, panel_id, nome)
        se não for pid:
            await Interaction.response.send_message("Produto não encontrado nesse painel.", ephemeral=True)
            retornar
        del estoque[pid]
        salvar_json(ARQUIVO_DE_AÇÕES, dados_de_ações)
        aguardar interação.resposta.defer(efêmero=True)
        aguardar atualização_painéis(interação.cliente, interação.id_guilda)
        aguardar interação.followup.send(f"Produto **{nome}** removido ✅", ephemeral=True)

    @remover.autocomplete("painel")
    async def remover_painel_ac(self, interaction: discord.Interaction, current: str):
        retornar aguardar painel_autocomplete(interação, atual)

    @remover.autocomplete("nome")
    async def remover_nome_ac(self, interaction: discord.Interaction, current: str):
        retornar aguardar produto_autocomplete(interação, atual)

    @app_commands.command(name="editar", description="Editar um produto de um painel de vendas")
    @app_commands.describe(
        nome="Nome do produto",
        preco="Novo preço (opcional)",
        quantidade="Nova quantidade (opcional)",
        descricao="Nova descrição (opcional)",
        painel="Em qual painel de vendas está o produto",
        preco_de="Preço antigo riscado no ticket (opcional — use 0 pra removedor)",
        imagem="Nova imagem do produto no ticket (opcional)",
    )
    async def editar(
        auto,
        interação: discord.Interação,
        nome: str,
        preco: float = None,
        quantidade: int = None,
        descrição: str = Nenhum,
        painel: str = Nenhum,
        preco_de: float = None,
        imagem: discord.Attachment = None,
    ):
        panel_id, erro = resolve_panel_id(interaction.guild_id, painel)
        se erro:
            aguardar interação.resposta.enviar_mensagem(erro, efêmero=True)
            retornar
        estoque = obter_estoque_da_guilda(interação.id_da_guilda)
        pid, produto = find_product(stock, panel_id, nome)
        se não for pid:
            await Interaction.response.send_message("Produto não encontrado nesse painel.", ephemeral=True)
            retornar
        se preco não for None:
            produto["preco"] = preço
        se não for Nenhum:
            produto["quantidade"] = quantidade
        se a descrição não for None:
            produto["descrição"] = descrição
        se preco_de não for None:
            produto["preco_de"] = preco_de if preco_de > 0 else Nenhum
        se a imagem não for None:
            novo_arquivo = aguardar salvar_imagem(imagem)
            apagar_imagem(produto.get("imagem_arquivo"))
            produto["imagem_url"] = imagem.url
            produto["imagem_arquivo"] = novo_arquivo
        salvar_json(ARQUIVO_DE_AÇÕES, dados_de_ações)
        aguardar interação.resposta.defer(efêmero=True)
        aguardar atualização_painéis(interação.cliente, interação.id_guilda)
        aguardar interação.followup.send(f"Produto **{nome}** atualizado ✅", efêmero=True)

    @editar.autocomplete("painel")
    async def editar_painel_ac(self, interaction: discord.Interaction, current: str):
        retornar aguardar painel_autocomplete(interação, atual)

    @editar.autocomplete("nome")
    async def editar_nome_ac(self, interaction: discord.Interaction, current: str):
        retornar aguardar produto_autocomplete(interação, atual)

    @app_commands.command(name="listar", description="Lista dos produtos de cada painel de vendas")
    @app_commands.describe(painel="Ver só um painel (opcional — sem isso mostra todos)")
    async def listar(self, interaction: discord.Interaction, painel: str = None):
        painéis = listar_painéis_de_vendas(interação.id_da_guilda)
        se não houver painéis:
            aguardar interação.resposta.enviar_mensagem(
                "Você ainda não tem nenhum painel de vendas. Crie um com /painel vendas.", ephemeral=True
            )
            retornar
        se painel:
            painéis = [p para p em painéis se str(p["message_id"]) == painel]
            se não houver painéis:
                aguarde interação.response.send_message("Painel não encontrado.", ephemeral=True)
                retornar

        estoque = obter_estoque_da_guilda(interação.id_da_guilda)
        embed = discord.Embed(title="📦 Estoque por painel", color=discord.Color.blurple())
        para p em painéis[:25]:
            pid_painel = str(p["id_mensagem"])
            linhas = []
            para prod em stock.values():
                Se prod.get("painel_id") != pid_painel:
                    continuar
                qtd = prod["quantidade"]
                estoque = "esgotado" if qtd <= 0 else f"estoque {qtd}"
                linhas.append(f"• **{prod['nome']}** — R$ {prod['preco']:.2f} ({estoque})")
            texto = "\n".join(linhas) ou "Nenhum produto ainda."
            se len(texto) > 1000:
                texto = texto[:997] + "..."
            embed.add_field(name=panel_label(interaction.guild, p), value=texto, inline=False)
        aguardar interação.resposta.enviar_mensagem(incorporado=incorporado, efêmero=verdadeiro)

    @listar.autocomplete("painel")
    async def listar_painel_ac(self, interaction: discord.Interaction, current: str):
        retornar aguardar painel_autocomplete(interação, atual)

    @app_commands.command(name="resetar", description="Apaga TODOS os produtos do estoque (pede confirmação)")
    @app_commands.describe(painel="Apagar apenas os produtos desse painel (sem isso, desligue todos os painéis)")
    async def resetar(self, interaction: discord.Interaction, painel: str = None):
        estoque = obter_estoque_da_guilda(interação.id_da_guilda)
        se painel:
            se painel não estiver em {str(p["message_id"]) para p em list_sales_panels(interaction.guild_id)}:
                aguarde interação.response.send_message("Painel não encontrado.", ephemeral=True)
                retornar
            total = soma(1 para p em stock.values() se p.get("painel_id") == painel)
            escopo = "do painel escolhido"
        outro:
            total = len(stock)
            escopo = "de **todos** os painéis"

        se total == 0:
            aguarde interação.response.send_message("Não tem nenhum produto pra apagar.", ephemeral=True)
            retornar

        aguardar interação.resposta.enviar_mensagem(
            f"⚠️ Isso vai apagar **{total} produto(s)** {escopo}, com todo o estoque deles. "
            "**Não dá pra desfazer.** O histórico de vendas (/saldo) continua guardado.\n\nConfirma?",
            view=ResetEstoqueView(interaction.user.id, interaction.guild_id, painel),
            efêmero=Verdadeiro,
        )

    @resetar.autocomplete("painel")
    async def resetar_painel_ac(self, interaction: discord.Interaction, current: str):
        retornar aguardar painel_autocomplete(interação, atual)


classe TicketOpcoesGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            nome="bilhete",
            description="Gerenciamento dos tipos de atendimento do painel de ticket de ajuda",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        se is_owner(interaction):
            retornar Verdadeiro
        raise app_commands.CheckFailure("Apenas o dono da loja pode gerenciar os tipos de ticket.")

    @app_commands.command(name="adicionar", description="Adiciona um tipo de atendimento (ex: Suporte, Erro no pagamento)")
    @app_commands.describe(nome="Nome do tipo de atendimento", descricao="Descrição curta que aparece no menu (opcional)")
    async def adicionar(self, interação: discord.Interaction, nome: str, descrição: str = ""):
        opções = obter_opções_de_ajuda_da_guilda(interação.id_da_guilda)
        oid = slugify(nome)
        se oid estiver em opções:
            await Interaction.response.send_message("Já existe um tipo com esse nome. Use /ticket remove primeiro.", ephemeral=True)
            retornar
        options[oid] = {"nome": nome, "descricao": descricao}
        help_options_data[str(interaction.guild_id)] ​​= opções
        salvar_json(ARQUIVO_DE_OPÇÕES_DE_AJUDA, dados_de_opções_de_ajuda)
        aguardar atualização_painéis_de_ajuda(interação.cliente, interação.id_da_guilda)
        await interação.response.send_message(f"Tipo de atendimento **{nome}** adicionado ✅", efêmero=True)

    @app_commands.command(name="remover", description="Remover um tipo de atendimento")
    @app_commands.describe(nome="Nome do tipo de atendimento")
    async def remover(self, interaction: discord.Interaction, nome: str):
        opções = obter_opções_de_ajuda_da_guilda(interação.id_da_guilda)
        oid = slugify(nome)
        Se oid não estiver nas opções:
            aguarde interação.response.send_message("Tipo de atendimento não encontrado.", ephemeral=True)
            retornar
        del opções[oid]
        help_options_data[str(interaction.guild_id)] ​​= opções
        salvar_json(ARQUIVO_DE_OPÇÕES_DE_AJUDA, dados_de_opções_de_ajuda)
        aguardar atualização_painéis_de_ajuda(interação.cliente, interação.id_da_guilda)
        await Interaction.response.send_message(f"Tipo de atendimento **{nome}** removido ✅", ephemeral=True)

    @app_commands.command(name="listar", description="Lista todos os tipos de atendimento cadastrados")
    def assíncrona listar(self, interação: discord.Interação):
        opções = obter_opções_de_ajuda_da_guilda(interação.id_da_guilda)
        se não houver opções:
            await Interaction.response.send_message("Nenhum tipo de atendimento cadastrado ainda.", ephemeral=True)
            retornar
        embed = discord.Embed(title="📞 Tipos de atendimento", color=discord.Color.blurple())
        para o em options.values():
            embed.add_field(name=o["nome"], value=o.get("descricao") or "—", inline=False)
        aguardar interação.resposta.enviar_mensagem(incorporado=incorporado, efêmero=verdadeiro)


# ----------------------------------------------------------------------------
# /painel — criação do painel de vendas com título, descrição e banner
# ----------------------------------------------------------------------------

async def reset_select_message(interaction: discord.Interaction, view: discord.ui.View):
    """Reedita a mensagem do painel com um menu novo. Sem isso o Discord continua
    mostrando o ✓ na última opção escolhida, como se o ticket ainda estivesse aberto."""
    Se interaction.message for None:
        retornar
    tentar:
        aguardar interação.mensagem.editar(visualização=visualização)
    exceto discord.HTTPException:
        passar


classe ProductSelect(discord.ui.Select):
    def __init__(self, guild_id: int, panel_id: str | None = None):
        estoque = obter_estoque_da_guilda(id_da_guilda)
        opções = []
        para pid, p em stock.items():
            Se panel_id não for None e p.get("painel_id") != panel_id:
                continuar #produto de outro painel
            estoque = "Esgotado" if p["quantidade"] <= 0 else p["quantidade"]
            opções.adicionar(
                discord.SelectOption(
                    label=p["nome"][:100],
                    description=f"R$ {p['preco']:.2f} | Estoque: {estoque}"[:100],
                    valor=pid,
                )
            )
            se len(opções) >= MAX_PRODUTOS_POR_PAINEL:
                quebrar
        se não houver opções:
            options = [discord.SelectOption(label="Sem produtos disponíveis", value="none")]
        super().__init__(
            placeholder="Selecione um produto...",
            opções=opções,
            custom_id="painel_product_select",
        )

    async def callback(self, interaction: discord.Interaction):
        tentar:
            aguarde self._handle(interação)
        finalmente:
            await reset_select_message(interaction, ProductSelectView(interaction.guild_id, str(interaction.message.id)))

    async def _handle(self, interaction: discord.Interaction):
        se self.values[0] == "nenhum":
            aguarde interação.response.send_message("Nenhum produto disponível no momento.", efêmero=True)
            retornar

        cfg = get_guild_config(interaction.guild_id)
        membro_role_id = cfg.get("cargo_membro_id")
        se membro_role_id e não any(r.id == membro_role_id para r em interaction.user.roles):
            role = interaction.guild.get_role(registr_role_id)
            nome_cargo = role.mention if role else "necessário"
            aguardar interação.resposta.enviar_mensagem(
                f"Você precisa do cargo {nome_cargo} para poder comprar aqui.", ephemeral=True
            )
            retornar

        await create_ticket(interaction, self.values[0])


classe ProductSelectView(discord.ui.View):
    def __init__(self, guild_id: int, panel_id: str | None = None):
        super().__init__(timeout=None)
        self.add_item(ProductSelect(guild_id, panel_id))


class PanelModal(discord.ui.Modal, title="Criar Painel de Vendas"):
    título = discord.ui.TextInput(label="Título do painel", max_length=256)
    descrição = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None, banner_arquivo: str | None = None):
        super().__init__()
        self.banner_url = banner_url
        self.banner_arquivo = banner_arquivo

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        cor = discord.Color(cfg["cor_embed"]) se cfg.get("cor_embed") não for None senão discord.Color.gold()

        # Embed único — barra colorida contínua do título até o banner, sem
        #parecem duas caixas separadas. O banner fica abaixo do texto.
        embed = discord.Embed(title=self.titulo.value, description=self.descricao.value, color=cor)
        se self.banner_url:
            embed.set_image(url=self.banner_url)

        # Publica como mensagem normal do canal (não como resposta do comando),
        # assim não aparece "usou /painel" acima da mensagem.
        # Cada painel tem seu próprio estoque: o id do painel é o id dessa mensagem.
        mensagem_do_painel = aguarde interação.canal.enviar(incorporação=incorporação, visualização=ProductSelectView(interação.guild_id, "novo"))
        adicionar_registro_do_painel(
            interaction.guild_id, interaction.channel_id, panel_message.id,
            self.banner_url, self.titulo.value, self.descricao.value, banner_arquivo=self.banner_arquivo,
        )
        Migrate_legacy_products() # se existem produtos antigos sem painel, o 1º painel adota eles
        await panel_message.edit(view=ProductSelectView(interaction.guild_id, str(panel_message.id)))

        tem_produtos = qualquer(
            p.get("painel_id") == str(panel_message.id) para p em get_guild_stock(interaction.guild_id).values()
        )
        aviso = (
            ""
            se tem_produtos
            else "\n\n⚠️ Esse painel começou **vazio** (cada painel tem seu próprio estoque). "
            "Use /estoque adicionar e escolha este painel no campo **painel** (só você vê este aviso)."
        )
        aguardar interação.response.send_message(f"Painel publicado ✅{aviso}", efêmero=True)


classe HelpTicketSelect(discord.ui.Select):
    def __init__(self, guild_id: int):
        options_dict = get_guild_help_options(guild_id)
        opções = []
        para oid, o em options_dict.items():
            opções.adicionar(
                discord.SelectOption(label=o["nome"][:100], description=(o.get("descricao") or "")[:100], value=oid)
            )
        se não houver opções:
            options = [discord.SelectOption(label="Sem tipos de atendimento cadastrados", value="none")]
        super().__init__(
            placeholder="Selecione o tipo de atendimento...",
            opções=opções,
            custom_id="help_ticket_type_select",
        )

    async def callback(self, interaction: discord.Interaction):
        tentar:
            se self.values[0] == "nenhum":
                aguardar interação.resposta.enviar_mensagem(
                    "Nenhum tipo de atendimento disponível no momento.", efêmero=True
                )
                retornar
            await create_help_ticket(interaction, self.values[0])
        finalmente:
            await reset_select_message(interaction, HelpTicketSelectView(interaction.guild_id))


classe HelpTicketSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(HelpTicketSelect(guild_id))


class HelpPanelModal(discord.ui.Modal, title="Criar Painel de Ticket de Ajuda"):
    título = discord.ui.TextInput(label="Título do painel", max_length=256)
    descrição = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        opções = obter_opções_de_ajuda_da_guilda(interação.id_da_guilda)
        cfg = get_guild_config(interaction.guild_id)
        cor = discord.Color(cfg["cor_embed"]) if cfg.get("cor_embed") is not None else discord.Color.blurple()

        embed = discord.Embed(title=self.titulo.value, description=self.descricao.value, color=cor)
        se self.banner_url:
            embed.set_image(url=self.banner_url)
        visualização = HelpTicketSelectView(interaction.guild_id)

        mensagem_do_painel = aguarde interação.canal.enviar(incorporado=incorporado, visualização=visualização)
        adicionar_registro_painel_de_ajuda(
            interaction.guild_id, interaction.channel_id, panel_message.id,
            self.banner_url, self.titulo.value, self.descricao.value,
        )

        aviso = (
            ""
            se houver opções
            else "\n\n⚠️ Nenhum tipo de atendimento cadastrado ainda — use /ticket adicionar (só você vê este aviso)."
        )
        aguardar interação.response.send_message(f"Painel de ticket de ajuda publicado ✅{aviso}", efêmero=True)


classe PainelGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            nome="painel",
            description="Crie os painéis de vendas ou de ticket de ajuda",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        se is_owner(interaction):
            retornar Verdadeiro
        raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")

    @app_commands.command(name="vendas", description="Crie o painel de vendas neste canal")
    @app_commands.describe(banner="Imagem do banner para o final do painel (opcional)")
    async def vendas(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url se banner senão Nenhum
        banner_arquivo = aguarda salvar_imagem(banner, "banner") if banner else Nenhum
        aguardar interação.resposta.send_modal(PanelModal(banner_url, banner_arquivo))

    @app_commands.command(name="ticket", description="Crie o painel de ticket de ajuda neste canal")
    @app_commands.describe(banner="Imagem do banner para o final do painel (opcional)")
    async def ticket(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url se banner senão Nenhum
        aguardar interação.resposta.enviar_modal(HelpPanelModal(banner_url))


# ----------------------------------------------------------------------------
# /mensagem — manda uma mensagem personalizada (texto livre + banner opcional)
# ----------------------------------------------------------------------------

class MensagemModal(discord.ui.Modal, title="Enviar Mensagem"):
    título = discord.ui.TextInput(label="Título (opcional)", required=False, max_length=256)
    texto = discord.ui.TextInput(
        label="Mensagem",
        estilo=discord.TextStyle.paragraph,
        comprimento_máximo=4000,
        placeholder="Dica: pra um link clicável, escreva [texto do link](https://exemplo.com)",
    )

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(description=self.texto.value, color=discord.Color.blurple())
        se self.titulo.value:
            embed.title = self.titulo.value
        se self.banner_url:
            embed.set_image(url=self.banner_url)

        aguardar interação.canal.enviar(embed=embed)
        await interaction.response.send_message("Mensagem enviada ✅", ephemeral=True)


@bot.tree.command(name="mensagem", description="Enviar uma mensagem personalizada neste canal, com banner opcional")
@app_commands.describe(banner="Imagem do banner para o final da mensagem (opcional)")
@app_commands.default_permissions(administrator=True)
@require_owner()
async def mensagem(interaction: discord.Interaction, banner: discord.Attachment = None):
    banner_url = banner.url se banner senão Nenhum
    aguardar interação.resposta.enviar_modal(MensagemModal(url_do_banner))


# ----------------------------------------------------------------------------
# /personalizar — recursos premium (precisa de chave resgatada em /configurar)
# ----------------------------------------------------------------------------

class CorModal(discord.ui.Modal, title="Cor dos painéis"):
    cor = discord.ui.TextInput(label="Cor em hexadecimal", placeholder="Ex: FF5733", max_length=7)

    async def on_submit(self, interaction: discord.Interaction):
        texto = self.cor.value.strip().lstrip("#")
        tentar:
            valor = int(texto, 16)
            se não (0 <= valor <= 0xFFFFFF):
                raise ValueError
        exceto ValueError:
            aguardar interação.resposta.enviar_mensagem(
                "Cor inválida — use um código hexadecimal, tipo `FF5733` ou `#FF5733`.", ephemeral=True
            )
            retornar
        cfg = get_guild_config(interaction.guild_id)
        cfg["cor_embed"] = valor
        config_data[str(interaction.guild_id)] ​​= cfg
        salvar_json(CONFIG_FILE, config_data)
        aguarde interação.response.send_message(f"Cor dos painéis atualizados ✅ (#{texto.upper()})", efêmero=True)


class BoasVindasModal(discord.ui.Modal, title="Mensagem de Boas-vindas"):
    título = discord.ui.TextInput(label="Título (opcional)", required=False, max_length=256)
    texto = discord.ui.TextInput(label="Mensagem", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, banner_url: str | None):
        super().__init__()
        self.banner_url = banner_url

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(interaction.guild_id)
        cfg["boasvindas_titulo"] = self.titulo.value ou Nenhum
        cfg["boasvindas_texto"] = self.texto.value
        se self.banner_url:
            cfg["boasvindas_banner_url"] = self.banner_url
        config_data[str(interaction.guild_id)] ​​= cfg
        salvar_json(CONFIG_FILE, config_data)

        aviso = "" if cfg.get("canal_boasvindas_id") else "\n\n⚠️ Defina o canal de boas-vindas em /configurar pra ativar."
        await interação.response.send_message(f"Mensagem de boas-vindas salva ✅{aviso}", ephemeral=True)


classe PersonalizarGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            nome="personalizar",
            description="[Premium] Personaliza a aparência do bot neste servidor",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        se interaction.user.id estiver em OWNER_USER_IDS:
            retornar Verdadeiro
        se não is_owner(interaction):
            raise app_commands.CheckFailure("Apenas o dono da loja pode usar este comando.")
        cfg = get_guild_config(interaction.guild_id)
        se não cfg.get("premium"):
            raise app_commands.CheckFailure(
                "🔒 Este é um recurso premium. Resgate uma chave em /configurar para desbloquear."
            )
        retornar Verdadeiro

    @app_commands.command(name="nome", description="Muda o apelido do bot neste servidor")
    @app_commands.describe(nome="Novo nome/apelido do bot neste servidor")
    async def nome(self, interaction: discord.Interaction, nome: str):
        tentar:
            aguardar interação.guild.me.edit(nick=nome)
            await interaction.response.send_message(f"Nome do bot alterado para **{nome}** ✅", ephemeral=True)
        exceto discord.Proibido:
            aguardar interação.resposta.enviar_mensagem(
                "Não tenho permissão para mudar meu apelido aqui — preciso da permissão 'Gerenciar Apelidos', "
                "e minha carga precisa estar acima de quem eu tento mudar (no caso, eu mesmo).",
                efêmero=Verdadeiro,
            )

    @app_commands.command(name="foto", description="Mudar a foto do perfil do bot neste servidor")
    @app_commands.describe(foto="Nova imagem de perfil do bot neste servidor")
    def assíncrona foto(self, interação: discord.Interaction, foto: discord.Attachment):
        aguardar interação.resposta.defer(efêmero=True)
        tentar:
            image_bytes = await foto.read()
            aguardar interação.guild.me.edit(avatar=image_bytes)
            await interaction.followup.send("Foto do bot alterada neste servidor ✅", ephemeral=True)
        exceto TypeError:
            aguardar interação.followup.send(
                "A versão do discord.py instalada nesse host ainda não suporta foto por servidor — "
                "atualize com `pip install -U discord.py` e tente de novo.",
                efêmero=Verdadeiro,
            )
        exceto discord.HTTPException como e:
            await interação.followup.send(f"Não consegui trocar a foto: {e}", ephemeral=True)

    @app_commands.command(name="banner", description="Mudar o banner do perfil do bot neste servidor")
    @app_commands.describe(banner="Nova imagem de banner de perfil do bot neste servidor")
    async def banner(self, interaction: discord.Interaction, banner: discord.Attachment):
        aguardar interação.resposta.defer(efêmero=True)
        tentar:
            image_bytes = await banner.read()
            aguardar interação.guild.me.edit(banner=image_bytes)
            await interaction.followup.send("Banner do bot alterado neste servidor ✅", ephemeral=True)
        exceto TypeError:
            aguardar interação.followup.send(
                "A versão do discord.py instalada nesse host ainda não suporta banner por servidor — "
                "atualize com `pip install -U discord.py` e tente de novo.",
                efêmero=Verdadeiro,
            )
        exceto discord.HTTPException como e:
            await interação.followup.send(f"Não consegui trocar o banner: {e}", ephemeral=True)

    @app_commands.command(name="cor", description="Muda a cor dos painéis de vendas/ticket neste servidor")
    def assíncrona cor(self, interação: discord.Interação):
        aguardar interação.resposta.enviar_modal(CorModal())

    @app_commands.command(name="boasvindas", description="Configurar mensagem automática para quem entra no servidor")
    @app_commands.describe(banner="Imagem do banner para o final da mensagem (opcional)")
    async def boasvindas(self, interaction: discord.Interaction, banner: discord.Attachment = None):
        banner_url = banner.url se banner senão Nenhum
        aguardar interação.resposta.enviar_modal(BoasVindasModal(url_do_banner))


# ----------------------------------------------------------------------------
# Sistema de ingressos
# ----------------------------------------------------------------------------

TICKET_CATEGORY_NAME = "🛒 Vendas de Ingressos"
TICKET_AJUDA_CATEGORY_NAME = "📞 Bilhete Ajuda"


async def get_or_create_ticket_category(guild: discord.Guild, cfg: dict) -> discord.CategoryChannel:
    # Usa uma categoria definida manualmente em /configurar, se existir e for válida
    cat_id = cfg.get("ticket_category_id")
    se cat_id:
        existente = guilda.get_channel(cat_id)
        se isinstance(existing, discord.CategoryChannel):
            retornar ao existente

    # Reaproveita a categoria padrão, se você já tiver sido criado antes
    para gato em guild.categories:
        se cat.name == TICKET_CATEGORY_NAME:
            gato de retorno

    cargos_da_equipe = obter_cargos_da_equipe(guilda, cfg)
    sobrescreve = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True),
    }
    para função em staff_roles:
        sobrescreve[função] = discord.PermissionOverwrite(view_channel=True)

    return await guild.create_category(TICKET_CATEGORY_NAME, overwrites=overwrites)


async def get_or_create_help_category(guild: discord.Guild, cfg: dict) -> discord.CategoryChannel:
    cat_id = cfg.get("ticket_ajuda_category_id")
    se cat_id:
        existente = guilda.get_channel(cat_id)
        se isinstance(existing, discord.CategoryChannel):
            retornar ao existente

    para gato em guild.categories:
        se cat.name == TICKET_AJUDA_CATEGORY_NAME:
            gato de retorno

    # Só dono, administrador e responsável por ticket enxergam essa categoria — vendedor NÃO tem acesso.
    funções_da_equipe = obter_ajuda_funções_da_equipe(guilda, cfg)
    sobrescreve = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True),
    }
    para função em staff_roles:
        sobrescreve[função] = discord.PermissionOverwrite(view_channel=True)

    return await guild.create_category(TICKET_AJUDA_CATEGORY_NAME, overwrites=overwrites)


def get_ticket_owner_id(guild_id: int, channel_id: int) -> int | None:
    gid = str(guild_id)
    para uid, cid em tickets_data.get(gid, {}).items():
        se cid == channel_id:
            retornar int(uid)
    retornar Nenhum


def get_help_ticket_owner_id(guild_id: int, channel_id: int) -> int | None:
    gid = str(guild_id)
    para uid, cid em help_tickets_data.get(gid, {}).items():
        se cid == channel_id:
            retornar int(uid)
    retornar Nenhum


async def remove_help_ticket_record(guild_id: int, channel_id: int):
    gid = str(guild_id)
    user_tickets = help_tickets_data.get(gid, {})
    para uid, cid em list(user_tickets.items()):
        se cid == channel_id:
            deletar user_tickets[uid]
    help_tickets_data[gid] = user_tickets
    salvar_json(ARQUIVO_DE_TICKETS_DE_AJUDA, dados_de_tickets_de_ajuda)


async def create_help_ticket(interaction: discord.Interaction, option_id: str):
    guilda = interação.guilda
    cfg = get_guild_config(guild.id)
    gid = str(guild.id)

    opções = obter_opções_de_ajuda_da_guilda(id_da_guilda)
    opção = opções.obter(id_da_opção)
    se não for uma opção:
        await Interaction.response.send_message("Este tipo de atendimento não existe mais.", ephemeral=True)
        retornar

    user_tickets = help_tickets_data.get(gid, {})
    existing_channel_id = user_tickets.get(str(interaction.user.id))
    se existing_channel_id:
        canal_existente = guild.get_channel(id_do_canal_existente)
        se não existir_canal:
            tentar:
                existing_channel = await guild.fetch_channel(existing_channel_id)
            exceto (discord.NotFound, discord.Forbidden):
                canal_existente = Nenhum
        se o canal já existir:
            aguardar interação.resposta.enviar_mensagem(
                f"Você já tem um ticket de ajuda em aberto: <#{existent_channel_id}>", ephemeral=True
            )
            retornar
        outro:
            del user_tickets[str(interaction.user.id)]
            help_tickets_data[gid] = user_tickets
            salvar_json(ARQUIVO_DE_TICKETS_DE_AJUDA, dados_de_tickets_de_ajuda)

    aguarde interação.response.send_message("Criando seu ticket de ajuda...", ephemeral=True)

    funções_da_equipe = obter_ajuda_funções_da_equipe(guilda, cfg)
    categoria = await get_or_create_help_category(guild, cfg)
    Se cfg.get("ticket_ajuda_category_id") != category.id:
        cfg["ticket_ajuda_category_id"] = category.id
        config_data[gid] = cfg
        salvar_json(CONFIG_FILE, config_data)

    sobrescreve = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interação.usuário: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, manage_threads=True
        ),
    }
    para função em staff_roles:
        sobrescreve[função] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_threads=True
        )

    channel_name = f"ticket-ajuda-{interaction.user.name}".lower().replace(" ", "-")[:90]
    canal = await guild.create_text_channel(name=nome_do_canal, category=category, overwrites=overwrites)

    user_tickets[str(interaction.user.id)] = channel.id
    help_tickets_data[gid] = user_tickets
    salvar_json(ARQUIVO_DE_TICKETS_DE_AJUDA, dados_de_tickets_de_ajuda)

    incorporar = discord.Embed(
        title=f"📞 Bilhete de Ajuda — {option['nome']}",
        description=option.get("descricao") ou "Descreva sua dúvida ou problema abaixo. Em breve alguém vai te atender.",
        cor=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Aberto por: {interaction.user}")

    menção = interação.usuário.menção + " " + " ".join(r.menção para r em funções_da_equipe)
    aguardar canal.send(content=menção, embed=embed, view=HelpTicketView())
    await channel.send("⏳ Aguarde, um administrador irá hospedar seu ticket em breve.")

    aguardar enviar_log(
        guild.id, message=f"📞 Ticket de ajuda aberto: {channel.mention} — {interaction.user.mention}."
    )


async def create_ticket(interaction: discord.Interaction, product_id: str):
    guilda = interação.guilda
    estoque = obter_estoque_da_guilda(id_da_guilda)
    cfg = get_guild_config(guild.id)

    Se o produto com o ID não estiver em estoque:
        aguarde interação.response.send_message("Este produto não existe mais.", ephemeral=True)
        retornar

    produto = estoque[id_do_produto]
    if produto["quantidade"] <= 0:
        aguarde interação.response.send_message("Produto esgotado no momento.", ephemeral=True)
        retornar

    gid = str(guild.id)
    user_tickets = tickets_data.get(gid, {})
    existing_channel_id = user_tickets.get(str(interaction.user.id))
    se existing_channel_id:
        canal_existente = guild.get_channel(id_do_canal_existente)
        se não existir_canal:
            tentar:
                existing_channel = await guild.fetch_channel(existing_channel_id)
            exceto (discord.NotFound, discord.Forbidden):
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
    ticket_info_data.setdefault(gid, {})[str(channel.id)] = {
        "produto": product_id,
        "comprador": interaction.user.id,
        "quantidade": 1,
    }
    save_json(TICKET_INFO_FILE, ticket_info_data)

    imagem_ref, imagem_file = await resolver_imagem_produto(guild, product)
    embed = build_pedido_embed(guild, interaction.user, product, 1, cfg, imagem=imagem_ref)

    mention = interaction.user.mention + " " + " ".join(r.mention for r in staff_roles)
    kwargs = {"file": imagem_file} if imagem_file else {}
    await channel.send(content=mention, embed=embed, view=PedidoView(), **kwargs)
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
    if ticket_info_data.get(gid, {}).pop(str(channel_id), None) is not None:
        save_json(TICKET_INFO_FILE, ticket_info_data)


def get_ticket_info(guild_id: int, channel_id: int) -> dict:
    return ticket_info_data.get(str(guild_id), {}).get(str(channel_id), {})


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
            qtd = max(1, int(info.get("quantidade") or 1))
            cupom = info.get("cupom")

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
                    product["quantidade"] = max(0, product["quantidade"] - qtd)
                    save_json(STOCK_FILE, stock_data)
                    subtotal, desconto, total = calcular_total(product, qtd, cupom)
                    record_sale(
                        interaction.guild_id, product["nome"], total, buyer_id or 0, interaction.user.id, quantidade=qtd
                    )
                    if cupom:
                        vivo = get_guild_coupons(interaction.guild_id).get(cupom["codigo"])
                        if vivo is not None:
                            vivo["usos"] = vivo.get("usos", 0) + 1
                            save_json(COUPONS_FILE, coupons_data)

                    comprador = f"<@{buyer_id}>" if buyer_id else "(desconhecido)"
                    log_texto = (
                            f"✅ Venda concluída: **{qtd}x {product['nome']}** ({brl(total)}"
                            f"{' com cupom ' + cupom['codigo'] if cupom else ''}) — "
                            f"comprador {comprador}, atendido por {interaction.user.mention}."
                    )
                    entrega_embed = discord.Embed(title=f"📦 {product['nome']}", color=discord.Color.green())
                    entrega_embed.add_field(name="Quantidade", value=str(qtd), inline=True)
                    entrega_embed.add_field(name="Total", value=brl(total), inline=True)
                    entrega_embed.add_field(name="Descrição", value=product["descricao"], inline=False)
                    entrega_embed.set_footer(text=f"Comprador: {comprador} | Atendido por: {interaction.user}")
                    carrinho_txt = f"{qtd}x {product['nome']}"
                    desc_txt = " ".join(str(product.get("descricao", "")).split())
                    if desc_txt:
                        carrinho_txt += f" • {desc_txt}"
                    card = {
                        "buyer_id": buyer_id,
                        "carrinho": carrinho_txt,
                        "valor": brl(total),
                        "link": link_do_painel(interaction.guild_id, product),
                    }
                    await send_delivery_log(interaction.guild_id, entrega_embed, card=card)
                    await send_log_card(interaction.guild_id, log_texto, card)
                    await refresh_panels(interaction.client, interaction.guild_id)
            except Exception as erro:  # noqa: BLE001
                print(f"[concluir] erro ao atualizar estoque/logs: {erro!r}")

            await asyncio.sleep(5)
            try:
                await interaction.channel.delete()
            finally:
                await remove_ticket_record(interaction.guild_id, canal_id)
                if product and buyer_id:
                    await send_rating_request(interaction.guild_id, buyer_id, interaction.user.id, product["nome"])
        finally:
            concluindo_tickets.discard(canal_id)

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
# Tela "Revisão do Pedido" — o primeiro que o comprador vê dentro do ticket
# (com cupom de desconto, imagem do produto e o cartão de entrega)
# ----------------------------------------------------------------------------

def brl(valor: float) -> str:
    """Formata no padrão brasileiro: 1234.5 -> 'R$ 1.234,50'."""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _codigo(texto, limite: int = 100) -> str:
    """Texto curto dentro de código inline (o fundo escuro da tela). Troca crases pra não quebrar a formatação."""
    texto = " ".join(str(texto).replace("`", "'").split())
    if not texto:
        return ""
    if len(texto) > limite:
        texto = texto[: limite - 1] + "…"
    return f"`{texto}`"


# ---- cupons ----------------------------------------------------------------

def get_guild_coupons(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in coupons_data:
        coupons_data[gid] = {}
        save_json(COUPONS_FILE, coupons_data)
    return coupons_data[gid]


def normalizar_cupom(c) -> dict | None:
    """Lê um cupom salvo em qualquer formato (inclusive de versões antigas do bot, que
    usavam outros nomes de campo) e devolve {'tipo': 'percent'|'fixo', 'valor': float}.
    Retorna None se não der pra entender."""
    if not isinstance(c, dict):
        return None
    tipo = str(c.get("tipo") or "").strip().lower()
    if tipo in ("percent", "porcentagem", "percentual", "percentage", "%"):
        tipo = "percent"
    elif tipo in ("fixo", "fixed", "reais", "valor", "brl", "r$"):
        tipo = "fixo"
    else:
        tipo = ""
    valor = c.get("valor")
    if valor is None:
        for k in ("porcentagem", "percent", "percentual"):
            if c.get(k) is not None:
                valor, tipo = c[k], tipo or "percent"
                break
    if valor is None:
        for k in ("valor_fixo", "fixo", "reais", "desconto", "value", "amount"):
            if c.get(k) is not None:
                valor, tipo = c[k], tipo or "fixo"
                break
    try:
        valor = float(str(valor).replace("%", "").replace("R$", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    if valor <= 0:
        return None
    return {"tipo": tipo or "fixo", "valor": valor}


def achar_cupom(guild_id: int, codigo: str):
    """Procura o cupom ignorando maiúsculas/minúsculas. Retorna (codigo_salvo, dados)."""
    alvo = (codigo or "").strip().upper()
    for chave, dados in get_guild_coupons(guild_id).items():
        if str(chave).strip().upper() == alvo:
            return chave, dados
    return None, None


def validar_cupom(guild_id: int, codigo: str):
    """Retorna (cupom, erro). O cupom volta como uma 'foto' (código, tipo, valor)
    que fica guardada no ticket — assim o desconto não muda no meio da compra."""
    chave, c = achar_cupom(guild_id, codigo)
    if not c:
        return None, "Cupom inválido."
    usos_max = c.get("usos_max", c.get("usos_maximo", c.get("limite"))) if isinstance(c, dict) else None
    try:
        if usos_max is not None and int(c.get("usos", 0)) >= int(usos_max):
            return None, "Esse cupom já foi usado o máximo de vezes."
    except (TypeError, ValueError):
        pass
    norm = normalizar_cupom(c)
    if norm is None:
        print(f"[cupom] cupom '{chave}' salvo em formato que não entendi: {c!r}")
        return None, "Esse cupom está com defeito. Peça pro dono apagar e criar de novo (/cupom remover e /cupom criar)."
    return {"codigo": str(chave).strip().upper(), "tipo": norm["tipo"], "valor": norm["valor"]}, None


def calcular_total(product: dict, quantidade: int, cupom: dict | None):
    """Retorna (subtotal, desconto, total). Cupom em % desconta do subtotal;
    cupom em reais desconta uma vez do pedido inteiro. Nunca passa de 100%."""
    subtotal = round(product["preco"] * quantidade, 2)
    desconto = 0.0
    if cupom:
        if cupom["tipo"] == "percent":
            desconto = subtotal * cupom["valor"] / 100
        else:
            desconto = cupom["valor"]
    desconto = round(min(max(desconto, 0.0), subtotal), 2)
    return subtotal, desconto, round(subtotal - desconto, 2)


def texto_desconto(cupom: dict) -> str:
    return f"{cupom['valor']:g}%" if cupom["tipo"] == "percent" else brl(cupom["valor"])


# ---- imagem do produto -----------------------------------------------------

async def salvar_imagem(anexo: discord.Attachment, prefixo: str = "produto") -> str | None:
    """Baixa a imagem pra pasta do bot. Link de anexo do Discord expira depois de um tempo,
    por isso a gente guarda o arquivo e reenvia ele junto com o ticket."""
    if anexo.content_type and not anexo.content_type.startswith("image/"):
        return None
    ext = os.path.splitext(anexo.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        ext = ".png"
    os.makedirs(IMAGES_DIR, exist_ok=True)
    nome = f"{prefixo}_{int(time.time())}_{random.randint(1000, 9999)}{ext}"
    try:
        await anexo.save(os.path.join(IMAGES_DIR, nome))
    except (discord.HTTPException, OSError):
        return None
    return nome


async def baixar_imagem_url(url: str, prefixo: str = "banner") -> str | None:
    """Baixa uma imagem de um link e guarda na pasta do bot (pra não depender de link que expira)."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as sessao:
            async with sessao.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return None
                tipo = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if not tipo.startswith("image/"):
                    return None
                dados = await r.read()
    except Exception as ex:  # noqa: BLE001
        print(f"[imagem] não consegui baixar {url[:60]}...: {ex!r}")
        return None
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(tipo, ".png")
    os.makedirs(IMAGES_DIR, exist_ok=True)
    nome = f"{prefixo}_{int(time.time())}_{random.randint(1000, 9999)}{ext}"
    try:
        with open(os.path.join(IMAGES_DIR, nome), "wb") as f:
            f.write(dados)
    except OSError:
        return None
    return nome


def apagar_imagem(nome: str | None):
    if not nome:
        return
    try:
        os.remove(os.path.join(IMAGES_DIR, nome))
    except OSError:
        pass


async def resolver_imagem_produto(guild: discord.Guild, product: dict):
    """Retorna (referência_da_imagem, arquivo_pra_anexar). Ordem: imagem do produto guardada
    no bot -> banner do painel (lido da própria mensagem do painel, que tem link sempre válido)
    -> link antigo guardado."""
    nome = product.get("imagem_arquivo")
    if nome:
        caminho = os.path.join(IMAGES_DIR, nome)
        if os.path.exists(caminho):
            return f"attachment://{nome}", discord.File(caminho, filename=nome)
    for p in get_guild_panels(guild.id):
        if str(p["message_id"]) == str(product.get("painel_id")):
            # 1) banner do painel guardado no bot (nunca expira)
            arq = p.get("banner_arquivo")
            if arq and os.path.exists(os.path.join(IMAGES_DIR, arq)):
                return f"attachment://{arq}", discord.File(os.path.join(IMAGES_DIR, arq), filename=arq)
            # 2) painel antigo: pega o banner da própria mensagem do painel e guarda uma cópia
            urls = []
            msg, _ = await _fetch_panel_message(bot, p)
            if msg is not None and msg.embeds and msg.embeds[0].image:
                urls += [msg.embeds[0].image.proxy_url, msg.embeds[0].image.url]
            urls.append(p.get("banner_url"))
            urls = [u for u in urls if u]
            for u in urls:
                salvo = await baixar_imagem_url(u, "banner")
                if salvo:
                    p["banner_arquivo"] = salvo
                    save_json(PANELS_FILE, panels_data)
                    return f"attachment://{salvo}", discord.File(os.path.join(IMAGES_DIR, salvo), filename=salvo)
            if urls:
                return urls[0], None
            break
    return product.get("imagem_url"), None


def link_do_painel(guild_id: int, product: dict) -> str | None:
    """Link pra mensagem do painel de onde o produto veio (vai no botão Comprar da entrega)."""
    for p in get_guild_panels(guild_id):
        if str(p["message_id"]) == str(product.get("painel_id")):
            return f"https://discord.com/channels/{guild_id}/{p['channel_id']}/{p['message_id']}"
    return None


# ---- cartão "Compra Aprovada" (imagem) ---------------------------------------

# Coloque Poppins-Regular.ttf e Poppins-Bold.ttf numa pasta "fonts" ao lado deste arquivo
# pra ficar idêntico ao modelo. Sem elas, o bot usa uma fonte parecida do sistema.
FONTS_DIRS = ["fonts", os.path.join(DATA_DIR, "fonts"), "."]
_FONTES = {
    "regular": [
        "Poppins-Regular.ttf", "/system/fonts/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf", "arial.ttf",
    ],
    "bold": [
        "Poppins-Bold.ttf", "/system/fonts/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf",
    ],
}
_cache_fontes: dict = {}


def _fonte(peso: str, tamanho: int):
    chave = (peso, tamanho)
    if chave in _cache_fontes:
        return _cache_fontes[chave]
    candidatos = []
    for nome in _FONTES[peso]:
        if os.sep in nome:
            candidatos.append(nome)
        else:
            candidatos += [os.path.join(pasta, nome) for pasta in FONTS_DIRS]
            candidatos.append(nome)
    fonte = None
    for c in candidatos:
        try:
            fonte = ImageFont.truetype(c, tamanho)
            break
        except OSError:
            continue
    if fonte is None:
        try:
            fonte = ImageFont.load_default(size=tamanho)
        except TypeError:  # Pillow antigo
            fonte = ImageFont.load_default()
    _cache_fontes[chave] = fonte
    return fonte


def render_card_compra(nome, usuario, avatar_bytes, carrinho, valor, loja, icone_bytes, creditos, quando) -> bytes:
    S = 3  # desenha em 3x e reduz no final, pra ficar com borda lisa
    W, H = 586, 292
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    FUNDO = (43, 45, 49, 255)
    LINHA = (63, 65, 71, 255)
    CINZA = (170, 173, 180, 255)
    BRANCO = (242, 243, 245, 255)
    VERDE = (87, 242, 135, 255)

    d.rounded_rectangle((0, 0, W * S - 1, H * S - 1), radius=26 * S, fill=FUNDO)

    def circulo(dados, cx, cy, diam):
        if dados:
            try:
                im = Image.open(io.BytesIO(dados)).convert("RGBA").resize((diam * S, diam * S), Image.LANCZOS)
            except Exception:  # noqa: BLE001
                im = None
        else:
            im = None
        if im is None:
            im = Image.new("RGBA", (diam * S, diam * S), (88, 101, 242, 255))
        mascara = Image.new("L", im.size, 0)
        ImageDraw.Draw(mascara).ellipse((0, 0, im.size[0] - 1, im.size[1] - 1), fill=255)
        img.paste(im, ((cx - diam // 2) * S, (cy - diam // 2) * S), mascara)

    def cabe(texto, fonte, largura):
        if d.textlength(texto, font=fonte) <= largura * S:
            return texto
        while texto and d.textlength(texto + "...", font=fonte) > largura * S:
            texto = texto[:-1]
        return texto.rstrip() + "..."

    def escreve(x, y, texto, fonte, cor, ancora="lm"):
        d.text((x * S, y * S), texto, font=fonte, fill=cor, anchor=ancora)

    PAD = 27
    DIR = W - PAD

    # cabeçalho: avatar, nome, @usuário e data
    circulo(avatar_bytes, PAD + 19, 49, 38)
    f_nome = _fonte("bold", 14 * S)
    escreve(90, 38, cabe(nome, f_nome, 300), f_nome, BRANCO)
    f_peq = _fonte("regular", 11 * S)
    escreve(90, 56, cabe("@" + usuario, f_peq, 300), f_peq, CINZA)
    escreve(DIR, 37, quando, f_peq, CINZA, "rm")

    # título com o check verde
    cy = 100
    d.ellipse((PAD * S, (cy - 13) * S, (PAD + 26) * S, (cy + 13) * S), fill=VERDE)
    pontos = [(PAD + 7, cy + 0.5), (PAD + 11.5, cy + 5), (PAD + 19.5, cy - 4.5)]
    d.line([(x * S, y * S) for x, y in pontos], fill=FUNDO, width=int(3 * S), joint="curve")
    escreve(PAD + 38, cy, "Compra Aprovada", _fonte("bold", 18 * S), BRANCO)

    # carrinho
    escreve(PAD, 138, "Carrinho", f_peq, CINZA)
    f_med = _fonte("regular", 14 * S)
    escreve(PAD, 158, cabe(carrinho, f_med, DIR - PAD), f_med, BRANCO)
    d.line((PAD * S, 178 * S, DIR * S, 178 * S), fill=LINHA, width=S)

    # valor pago
    escreve(PAD, 200, "Valor pago", f_peq, CINZA)
    escreve(DIR, 202, valor, _fonte("bold", 18 * S), VERDE, "rm")
    d.line((PAD * S, 225 * S, DIR * S, 225 * S), fill=LINHA, width=S)

    # rodapé: ícone + nome da loja, e os créditos à direita
    x_txt = PAD
    if icone_bytes:
        circulo(icone_bytes, PAD + 10, 249, 20)
        x_txt = PAD + 28
    escreve(x_txt, 249, cabe(loja, f_peq, 280), f_peq, CINZA)
    escreve(DIR, 249, creditos, f_peq, CINZA, "rm")

    img = img.resize((W * 2, H * 2), Image.LANCZOS)
    saida = io.BytesIO()
    img.save(saida, "PNG")
    return saida.getvalue()


async def montar_card_compra(guild: discord.Guild, buyer_id: int | None, carrinho: str, valor: str):
    """Monta o cartão 'Compra Aprovada' como imagem. Retorna None se não tiver Pillow."""
    if not PIL_OK:
        return None
    usuario = guild.get_member(buyer_id) if buyer_id else None
    if usuario is None and buyer_id:
        try:
            usuario = await bot.fetch_user(buyer_id)
        except discord.HTTPException:
            usuario = None

    avatar = None
    if usuario is not None:
        nome, arroba = usuario.display_name, usuario.name
        try:
            avatar = await usuario.display_avatar.replace(size=128, format="png").read()
        except Exception:  # noqa: BLE001
            avatar = None
    else:
        nome, arroba = "Cliente", "desconhecido"

    icone = None
    if guild.icon:
        try:
            icone = await guild.icon.replace(size=64, format="png").read()
        except Exception:  # noqa: BLE001
            icone = None

    agora = datetime.now(timezone(timedelta(hours=-3)))  # horário de Brasília
    png = await asyncio.to_thread(
        render_card_compra,
        nome, arroba, avatar, carrinho, valor, guild.name, icone,
        f"Powered by {bot.user.name}", agora.strftime("%d/%m · %H:%M"),
    )
    return discord.File(io.BytesIO(png), filename="compra-aprovada.png")


# ---- Revisão do Pedido -------------------------------------------------------

def build_pedido_embed(
    guild: discord.Guild, member, product: dict, quantidade: int, cfg: dict,
    imagem: str | None = None, cupom: dict | None = None,
) -> discord.Embed:
    cor = discord.Color(cfg["cor_embed"]) if cfg.get("cor_embed") is not None else discord.Color.teal()
    embed = discord.Embed(title="Revisão do Pedido", color=cor, timestamp=discord.utils.utcnow())
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

    preco = product["preco"]
    preco_de = product.get("preco_de")
    linhas = []
    if preco_de and preco_de > preco:
        linhas.append(f"De : ~~`{brl(preco_de)}`~~")
    linhas.append(f"Para : `{brl(preco)}`")
    embed.add_field(name="Valor à vista", value="\n".join(linhas), inline=False)

    embed.add_field(name="📦 Em estoque", value=f"`{product['quantidade']}`", inline=False)

    subtotal, desconto, total = calcular_total(product, quantidade, cupom)
    carrinho = f"`{quantidade}x` {_codigo(product['nome'], 80)}"
    descricao = _codigo(product.get("descricao", ""), 100)
    if descricao:
        carrinho += f" - {descricao}"
    carrinho += f" | `{brl(subtotal)}`"
    embed.add_field(name="Carrinho", value=carrinho, inline=False)

    if cupom:
        embed.add_field(
            name="🎟️ Cupom",
            value=f"`{cupom['codigo']}` ({texto_desconto(cupom)}) | `-{brl(desconto)}`",
            inline=False,
        )
        embed.add_field(name="Total", value=f"`{brl(total)}`", inline=False)

    if imagem:
        embed.set_image(url=imagem)
    return embed


def _pode_mexer_no_pedido(interaction: discord.Interaction) -> bool:
    """Só o comprador do ticket e a equipe mexem no pedido."""
    info = get_ticket_info(interaction.guild_id, interaction.channel_id)
    comprador = info.get("comprador") or get_ticket_owner_id(interaction.guild_id, interaction.channel_id)
    return interaction.user.id == comprador or is_admin(interaction)


def _imagem_da_mensagem(message) -> str | None:
    if message is None:
        return None
    # se a imagem foi enviada como anexo junto da mensagem, continua apontando pro anexo
    # (o link direto expira; o anexo some só quando a mensagem some)
    if message.attachments and message.embeds and message.embeds[0].image:
        return f"attachment://{message.attachments[0].filename}"
    if message.embeds:
        return message.embeds[0].image.url
    return None


def _embed_do_pedido(interaction: discord.Interaction, info: dict, product: dict) -> discord.Embed:
    comprador_id = info.get("comprador")
    membro = interaction.guild.get_member(comprador_id) if comprador_id else None
    return build_pedido_embed(
        interaction.guild, membro or interaction.user, product,
        max(1, int(info.get("quantidade") or 1)), get_guild_config(interaction.guild_id),
        imagem=_imagem_da_mensagem(interaction.message), cupom=info.get("cupom"),
    )


class QuantidadeModal(discord.ui.Modal, title="Editar Quantidade"):
    def __init__(self, atual: int, maximo: int):
        super().__init__()
        self.maximo = maximo
        self.qtd = discord.ui.TextInput(
            label=f"Quantidade (1 a {maximo})", default=str(atual), min_length=1, max_length=4
        )
        self.add_item(self.qtd)

    async def on_submit(self, interaction: discord.Interaction):
        texto = self.qtd.value.strip()
        if not texto.isdigit() or not (1 <= int(texto) <= self.maximo):
            await interaction.response.send_message(f"Digite um número de 1 a {self.maximo}.", ephemeral=True)
            return
        info = get_ticket_info(interaction.guild_id, interaction.channel_id)
        product = get_guild_stock(interaction.guild_id).get(info.get("produto"))
        if not product:
            await interaction.response.send_message("Este produto não existe mais.", ephemeral=True)
            return
        info["quantidade"] = int(texto)
        save_json(TICKET_INFO_FILE, ticket_info_data)
        await interaction.response.edit_message(embed=_embed_do_pedido(interaction, info, product), view=PedidoView())


class CupomModal(discord.ui.Modal, title="Usar Cupom"):
    codigo = discord.ui.TextInput(
        label="Código do cupom", placeholder="Deixe vazio pra remover o cupom do pedido",
        required=False, max_length=32,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not _pode_mexer_no_pedido(interaction):
            await interaction.response.send_message("Só quem abriu o ticket pode mexer no pedido.", ephemeral=True)
            return
        info = get_ticket_info(interaction.guild_id, interaction.channel_id)
        product = get_guild_stock(interaction.guild_id).get(info.get("produto"))
        if not product:
            await interaction.response.send_message("Este produto não existe mais.", ephemeral=True)
            return
        texto = self.codigo.value.strip()
        if texto:
            try:
                cupom, erro = validar_cupom(interaction.guild_id, texto)
            except Exception as ex:  # noqa: BLE001
                print(f"[cupom] erro ao validar '{texto}': {ex!r}")
                cupom, erro = None, "Não consegui validar esse cupom agora. Avise a administração."
            if erro:
                await interaction.response.send_message(f"❌ {erro}", ephemeral=True)
                return
            info["cupom"] = cupom
        else:
            if not info.get("cupom"):
                await interaction.response.send_message("Digite o código do cupom.", ephemeral=True)
                return
            info.pop("cupom")
        save_json(TICKET_INFO_FILE, ticket_info_data)
        await interaction.response.edit_message(embed=_embed_do_pedido(interaction, info, product), view=PedidoView())


class PedidoView(discord.ui.View):
    """Botões da Revisão do Pedido. Sem estado próprio (lê tudo do registro do ticket),
    então é persistente e continua funcionando depois de reiniciar o bot."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ir para o Pagamento", emoji="✔️", style=discord.ButtonStyle.success,
        custom_id="pedido_pagar", row=0,
    )
    async def pagar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _pode_mexer_no_pedido(interaction):
            await interaction.response.send_message("Só quem abriu o ticket pode mexer no pedido.", ephemeral=True)
            return
        info = get_ticket_info(interaction.guild_id, interaction.channel_id)
        product = get_guild_stock(interaction.guild_id).get(info.get("produto"))
        if not product:
            await interaction.response.send_message("Este produto não existe mais.", ephemeral=True)
            return
        qtd = max(1, int(info.get("quantidade") or 1))
        if product["quantidade"] < qtd:
            await interaction.response.send_message(
                f"O estoque mudou: restam só {product['quantidade']}. Ajuste em **Editar Quantidade**.",
                ephemeral=True,
            )
            return

        # Confere de novo o cupom (pode ter acabado os usos desde que foi aplicado)
        cupom = info.get("cupom")
        if cupom:
            _, erro = validar_cupom(interaction.guild_id, cupom["codigo"])
            if erro:
                info.pop("cupom", None)
                save_json(TICKET_INFO_FILE, ticket_info_data)
                await interaction.response.send_message(
                    f"⚠️ {erro} O cupom saiu do pedido — confira o novo total e clique de novo.", ephemeral=True
                )
                try:
                    await interaction.message.edit(embed=_embed_do_pedido(interaction, info, product))
                except discord.HTTPException:
                    pass
                return

        # Tira os botões da revisão (o pedido fica fechado) e abre a etapa de pagamento.
        await interaction.response.edit_message(view=None)

        cfg = get_guild_config(interaction.guild_id)
        cor = discord.Color(cfg["cor_embed"]) if cfg.get("cor_embed") is not None else discord.Color.teal()
        pix = cfg.get("pix")
        _, desconto, total = calcular_total(product, qtd, cupom)
        embed = discord.Embed(title="💳 Pagamento via PIX", color=cor)
        embed.add_field(name="Total a pagar", value=f"`{brl(total)}`", inline=False)
        if cupom:
            embed.add_field(name="🎟️ Cupom", value=f"`{cupom['codigo']}` | `-{brl(desconto)}`", inline=False)
        if pix:
            embed.description = "Faça o pagamento e aguarde a equipe confirmar."
            embed.add_field(name="Chave PIX", value=f"```{pix}```", inline=False)
        else:
            embed.description = "A chave PIX ainda não foi configurada — aguarde a equipe te passar os dados."
        await interaction.followup.send(embed=embed, view=TicketView())

    @discord.ui.button(
        label="Editar Quantidade", emoji="✏️", style=discord.ButtonStyle.primary,
        custom_id="pedido_quantidade", row=1,
    )
    async def quantidade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _pode_mexer_no_pedido(interaction):
            await interaction.response.send_message("Só quem abriu o ticket pode mexer no pedido.", ephemeral=True)
            return
        info = get_ticket_info(interaction.guild_id, interaction.channel_id)
        product = get_guild_stock(interaction.guild_id).get(info.get("produto"))
        if not product or product["quantidade"] <= 0:
            await interaction.response.send_message("Este produto está esgotado no momento.", ephemeral=True)
            return
        await interaction.response.send_modal(
            QuantidadeModal(int(info.get("quantidade") or 1), product["quantidade"])
        )

    @discord.ui.button(
        label="Usar Cupom", emoji="🎟️", style=discord.ButtonStyle.secondary,
        custom_id="pedido_cupom", row=1,
    )
    async def cupom(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _pode_mexer_no_pedido(interaction):
            await interaction.response.send_message("Só quem abriu o ticket pode mexer no pedido.", ephemeral=True)
            return
        await interaction.response.send_modal(CupomModal())

    @discord.ui.button(
        label="Adicionar produto", emoji="🛒", style=discord.ButtonStyle.secondary,
        custom_id="pedido_adicionar", row=2,
    )
    async def adicionar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🛒 Cada pedido tem um produto só por enquanto. Finalize este e abra outro ticket pelo painel.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Cancelar", emoji="🗑️", style=discord.ButtonStyle.danger,
        custom_id="pedido_cancelar", row=2,
    )
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _pode_mexer_no_pedido(interaction):
            await interaction.response.send_message("Só quem abriu o ticket pode cancelar o pedido.", ephemeral=True)
            return
        await interaction.response.send_message("Pedido cancelado. Fechando o ticket em instantes...", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete()
        finally:
            await remove_ticket_record(interaction.guild_id, interaction.channel_id)
            await send_log(interaction.guild_id, message=f"🗑️ Pedido cancelado por {interaction.user.mention}.")


# ---- /cupom — o dono cria os cupons de desconto -------------------------------

class CupomGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="cupom",
            description="Cupons de desconto para os tickets de venda",
            default_permissions=discord.Permissions(administrator=True),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_owner(interaction):
            return True
        raise app_commands.CheckFailure("Apenas o dono da loja pode gerenciar cupons.")

    @app_commands.command(name="criar", description="Cria um cupom de desconto")
    @app_commands.describe(
        codigo="O código que o cliente digita (letras, números, - e _)",
        porcentagem="Desconto em % (1 a 100) — use este OU o valor em reais",
        valor="Desconto em reais, tirado uma vez do pedido — use este OU a porcentagem",
        usos="Quantas vezes o cupom pode ser usado (vazio = ilimitado)",
    )
    async def criar(
        self,
        interaction: discord.Interaction,
        codigo: str,
        porcentagem: app_commands.Range[int, 1, 100] = None,
        valor: app_commands.Range[float, 0.01, 100000.0] = None,
        usos: app_commands.Range[int, 1, 1000000] = None,
    ):
        codigo = codigo.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{2,32}", codigo):
            await interaction.response.send_message(
                "Código inválido: use de 2 a 32 letras, números, - ou _ (sem espaços).", ephemeral=True
            )
            return
        if (porcentagem is None) == (valor is None):
            await interaction.response.send_message(
                "Escolha **um** tipo de desconto: ou `porcentagem` ou `valor` (não os dois).", ephemeral=True
            )
            return
        cupons = get_guild_coupons(interaction.guild_id)
        if codigo in cupons:
            await interaction.response.send_message(
                "Já existe um cupom com esse código. Remova ele antes com /cupom remover.", ephemeral=True
            )
            return
        cupons[codigo] = {
            "tipo": "percent" if porcentagem is not None else "fixo",
            "valor": float(porcentagem if porcentagem is not None else valor),
            "usos_max": usos,
            "usos": 0,
        }
        save_json(COUPONS_FILE, coupons_data)
        desconto = f"{porcentagem}%" if porcentagem is not None else brl(valor)
        limite = f"{usos} uso(s)" if usos else "usos ilimitados"
        await interaction.response.send_message(
            f"🎟️ Cupom **{codigo}** criado: **{desconto}** de desconto, {limite}.", ephemeral=True
        )

    @app_commands.command(name="remover", description="Apaga um cupom")
    @app_commands.describe(codigo="Código do cupom")
    async def remover(self, interaction: discord.Interaction, codigo: str):
        cupons = get_guild_coupons(interaction.guild_id)
        codigo = codigo.strip().upper()
        if codigo not in cupons:
            await interaction.response.send_message("Cupom não encontrado.", ephemeral=True)
            return
        del cupons[codigo]
        save_json(COUPONS_FILE, coupons_data)
        await interaction.response.send_message(f"🗑️ Cupom **{codigo}** removido.", ephemeral=True)

    @remover.autocomplete("codigo")
    async def remover_ac(self, interaction: discord.Interaction, current: str):
        cupons = get_guild_coupons(interaction.guild_id)
        return [
            app_commands.Choice(name=c, value=c) for c in cupons if current.upper() in c
        ][:25]

    @app_commands.command(name="listar", description="Mostra os cupons e quantas vezes cada um foi usado")
    async def listar(self, interaction: discord.Interaction):
        cupons = get_guild_coupons(interaction.guild_id)
        if not cupons:
            await interaction.response.send_message(
                "Nenhum cupom criado ainda. Use /cupom criar.", ephemeral=True
            )
            return
        linhas = []
        for codigo, c in list(cupons.items())[:25]:
            limite = c.get("usos_max", c.get("usos_maximo", c.get("limite")))
            usos = f"{c.get('usos', 0)}/{limite}" if limite else f"{c.get('usos', 0)} (ilimitado)"
            norm = normalizar_cupom(c)
            desc = texto_desconto(norm) if norm else "⚠️ formato inválido (recrie)"
            linhas.append(f"`{codigo}` — {desc} — usos: {usos}")
        embed = discord.Embed(title="🎟️ Cupons", description="\n".join(linhas), color=discord.Color.teal())
        await interaction.response.send_message(embed=embed, ephemeral=True)


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
# Registro de comandos e tratamento de erros
# ----------------------------------------------------------------------------

bot.tree.add_command(EstoqueGroup())
bot.tree.add_command(PainelGroup())
bot.tree.add_command(TicketOpcoesGroup())
bot.tree.add_command(PersonalizarGroup())
bot.tree.add_command(SorteioGroup())
bot.tree.add_command(EntradasGroup())
bot.tree.add_command(CupomGroup())


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
    bot.add_view(PedidoView())
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
