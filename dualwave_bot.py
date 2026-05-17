import json
import os
import random
import string
import datetime
import asyncio
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ✅ CONFIGURAÇÃO BÁSICA
TOKEN = "8604175238:AAGxFrEPmKAphECy-gvJdbFMjFU6uA4UwqA"
ADMIN_ID = 8182769178
NOME_BOT = "DualWave"
USERS_FILE = "usuarios.json"
PENDENTES_FILE = "pendentes.json"
RATE = 70  # 1 USD = 70 MZN

# ✅ DICIONÁRIO DE TRADUÇÃO
TEXTOS = {
    "pt": {
        "welcome": "🤖 *Bem-vindo ao DualWave*, {nome}!\n\nSeu assistente de investimento bilíngue.\nMoedas suportadas: USD & MZN.",
        "lang_choose": "Escolha seu idioma / Choose your language:",
        "main_menu": "📚 Menu de Comandos",
        "btn_planos": "💼 Ver Planos",
        "btn_saldo": "💰 Meu Saldo",
        "btn_ajuda": "📚 Ajuda",
        "btn_coletar": "📈 Coletar Lucros",
        "btn_team": "👥 Equipe",
        "insufficient": "❌ Saldo insuficiente.",
        "min_dep": "Valor mínimo para depósito é 5 USD (~350 MZN).",
        "wait_admin": "Aguarde aprovação do administrador.",
        "collect_done": "✅ Lucros coletados com sucesso!",
        "already_collected": "⏳ Você já coletou hoje!"
    },
    "en": {
        "welcome": "🤖 *Welcome to DualWave*, {nome}!\n\nYour bilingual investment assistant.\nSupported currencies: USD & MZN.",
        "lang_choose": "Choose your language:",
        "main_menu": "📚 Command Menu",
        "btn_planos": "💼 View Plans",
        "btn_saldo": "💰 My Balance",
        "btn_ajuda": "📚 Help",
        "btn_coletar": "📈 Collect Profits",
        "btn_team": "👥 Team",
        "insufficient": "❌ Insufficient balance.",
        "min_dep": "Minimum deposit is 5 USD (~350 MZN).",
        "wait_admin": "Wait for admin approval.",
        "collect_done": "✅ Profits collected successfully!",
        "already_collected": "⏳ You already collected today!"
    }
}

# ✅ FUNÇÕES AUXILIARES
def carregar_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

def salvar_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def gerar_id(tamanho=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=tamanho))

def fmt(valor_mzn):
    """Converte MZN para USD e retorna string formatada com ambos"""
    valor_usd = valor_mzn / RATE
    return f"{valor_usd:.2f} USD ~ {valor_mzn:.2f} MZN"

def get_planos_disponiveis():
    return {
        "🌊 Wave Starter":    {"preco": 350,    "percent": 0.07, "dias": 25, "max": 1},
        "🌊 Silver Wave":     {"preco": 1500,   "percent": 0.07, "dias": 30, "max": 2},
        "🌊 Golden Wave":     {"preco": 3500,   "percent": 0.08, "dias": 30, "max": 3},
        "🌊 Platinum Wave":   {"preco": 10500,  "percent": 0.08, "dias": 45, "max": 5},
        "🌊 Diamond Wave":    {"preco": 100000, "percent": 0.10, "dias": 60, "max": 10},
    }

# ✅ HANDLERS PRINCIPAIS
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    uid = str(u.id)
    
    usuarios = carregar_json(USERS_FILE)
    
    if uid not in usuarios:
        usuarios[uid] = {
            "nome": u.first_name,
            "saldo": 0,
            "planos": [],
            "indicador": ctx.args[0] if ctx.args else None,
            "indicados": [],
            "lang": "pt", # Default
            "historico": [],
            "last_coleta_date": "Nunca"
        }
        salvar_json(USERS_FILE, usuarios)
        
        # Menu de Idioma no primeiro acesso
        buttons = [[InlineKeyboardButton("🇧🇷 Português", callback_data="setlang|pt"),
                    InlineKeyboardButton("🇺🇸 English", callback_data="setlang|en")]]
        return await update.message.reply_text(TEXTOS["pt"]["lang_choose"], reply_markup=InlineKeyboardMarkup(buttons))

    await mostrar_menu_principal(update, ctx, usuarios[uid])

async def set_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("|")[1]
    uid = str(update.effective_user.id)
    
    usuarios = carregar_json(USERS_FILE)
    usuarios[uid]["lang"] = lang
    salvar_json(USERS_FILE, usuarios)
    
    await mostrar_menu_principal(update, ctx, usuarios[uid], edit=True)

async def mostrar_menu_principal(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user, edit=False):
    lang = user["lang"]
    t = TEXTOS[lang]
    nome = user["nome"]
    
    msg = t["welcome"].format(nome=nome)
    buttons = [
        [InlineKeyboardButton(t["btn_planos"], callback_data="planos"), InlineKeyboardButton(t["btn_saldo"], callback_data="ajuda_saldo")],
        [InlineKeyboardButton(t["btn_coletar"], callback_data="ajuda_coletar"), InlineKeyboardButton(t["btn_team"], callback_data="ajuda_indicacao")],
        [InlineKeyboardButton("🌍 Language / Idioma", callback_data="choose_lang")]
    ]
    
    if edit:
        await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

# ✅ LÓGICA DE SALDO (DUAL CURRENCY)
async def ajuda_saldo_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    usuarios = carregar_json(USERS_FILE)
    user = usuarios[uid]
    lang = user["lang"]
    
    saldo_mzn = user.get("saldo", 0)
    
    msg = (
        f"💰 **{TEXTOS[lang]['btn_saldo']}**\n\n"
        f"💵 **Total:** `{fmt(saldo_mzn)}`\n"
        f"📊 Planos Ativos: {len(user.get('planos', []))}\n"
    )
    
    buttons = [
        [InlineKeyboardButton("📥 Depósito", callback_data="ajuda_depositar"), InlineKeyboardButton("📤 Saque", callback_data="ajuda_sacar")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="ajuda_start")]
    ]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

# ==========================================
# 📥 SISTEMA DE DEPÓSITO - DUALWAVE
# ==========================================

# 1. ESCOLHA DO MÉTODO (Início)
async def ajuda_depositar_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try: await query.message.delete()
    except: pass

    lang = carregar_json(USERS_FILE).get(str(query.from_user.id), {}).get("lang", "pt")
    msg = "📥 **DEPÓSITO / DEPOSIT**\n\nSelecione o método de pagamento:\nSelect payment method:"
    
    kb = [
        [InlineKeyboardButton("🇲🇿 M-Pesa", callback_data="dep_metodo|M-Pesa")],
        [InlineKeyboardButton("🇲🇿 E-Mola", callback_data="dep_metodo|E-Mola")],
        [InlineKeyboardButton("🌐 USDT (BEP20)", callback_data="dep_metodo|Crypto")],
        [InlineKeyboardButton("⬅️ Voltar / Back", callback_data="ajuda_saldo")]
    ]
    await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# 2. ESCOLHA DO VALOR
async def dep_metodo_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    metodo = query.data.split("|")[1]
    ctx.user_data["dep_mtd"] = metodo
    try: await query.message.delete()
    except: pass

    msg = f"✅ **Método:** {metodo}\n\n💰 **Quanto deseja depositar?**\nDigite o valor em MZN (Mínimo: 350 MZN):"
    ctx.user_data["esperando_val_dep"] = True
    await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# 3. LÓGICA DE TEXTO (VALOR E HASH) - ADICIONAR DENTRO DA SUA FUNÇÃO 'tratar_mensagens'
async def tratar_mensagens_deposito(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text
    
    # PASSO A: RECEBER VALOR E MOSTRAR DADOS
    if ctx.user_data.get("esperando_val_dep"):
        try:
            valor = float(text)
            if valor < 350: raise ValueError
            ctx.user_data["dep_val"] = valor
            ctx.user_data["esperando_val_dep"] = False
            ctx.user_data["esperando_hash"] = True # Novo passo
            
            metodo = ctx.user_data["dep_mtd"]
            titular = "DualWave Official"
            contas = {"M-Pesa": "849564273", "E-Mola": "877329951", "Crypto": "0x0df8e7b0c172f509f6aff2791fb500462b13a5e5"}
            
            msg = (
                f"⚠️ **DADOS DE PAGAMENTO**\n\n"
                f"💵 **Valor:** {fmt(valor)}\n"
                f"🏛️ **Método:** {metodo}\n"
                f"👤 **Titular:** {titular}\n"
                f"📱 **Número/Carteira:** `{contas[metodo]}`\n\n"
                "------------------------------------------\n"
                "📌 **INSTRUÇÕES:**\n"
                "1. Faça a transferência.\n"
                "2. Copie o **ID da Transação / Hash** da mensagem de confirmação.\n"
                "3. **Cole o ID/Hash aqui no chat agora:** 👇"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ Valor inválido. Mínimo 350 MZN.")

    # PASSO B: RECEBER HASH E PEDIR FOTO
    elif ctx.user_data.get("esperando_hash"):
        ctx.user_data["dep_hash"] = text
        ctx.user_data["esperando_hash"] = False
        ctx.user_data["esperando_img_dep"] = True
        
        await update.message.reply_text(
            "✅ **ID/Hash recebido!**\n\n📸 Agora, para finalizar, envie a **Foto do Comprovante**:",
            parse_mode=ParseMode.MARKDOWN
        )

# 4. RECEBER FOTO E ENVIAR PARA ADMIN
async def tratar_comprovante(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("esperando_img_dep"): return
    
    photo = update.message.photo[-1].file_id
    pid = gerar_id()
    uid = str(update.effective_user.id)
    u_nome = update.effective_user.first_name
    hora = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    
    valor = ctx.user_data["dep_val"]
    metodo = ctx.user_data["dep_mtd"]
    tx_hash = ctx.user_data["dep_hash"]
    
    # Salva nos pendentes
    pendentes = carregar_json(PENDENTES_FILE)
    pendentes[pid] = {"user_id": uid, "valor": valor, "mtd": metodo, "hash": tx_hash, "tipo": "deposito"}
    salvar_json(PENDENTES_FILE, pendentes)
    
    # Notifica Admin Detalhado
    caption_admin = (
        f"💰 **NOVA SOLICITAÇÃO DE DEPÓSITO**\n\n"
        f"👤 **Usuário:** {u_nome}\n"
        f"🆔 **ID Usuário:** `{uid}`\n"
        f"🕒 **Hora:** {hora}\n"
        f"🏛️ **Método:** {metodo}\n"
        f"💵 **Valor:** {fmt(valor)}\n"
        f"🔗 **ID Transação/Hash:** `{tx_hash}`\n"
        f"🎫 **ID Depósito:** `{pid}`"
    )
    
    await ctx.bot.send_photo(
        ADMIN_ID, photo=photo, caption=caption_admin, parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar|{pid}"),
            InlineKeyboardButton("❌ Recusar", callback_data=f"recusar|{pid}")
        ]])
    )

    msg_final = (
        "🚀 **PROCESSANDO DEPÓSITO!**\n\n"
        f"Sua solicitação de {fmt(valor)} foi enviada.\n"
        "⏳ **Tempo:** 1 a 30 minutos.\n\n"
        "Caso não seja aprovado no prazo, contacte o suporte.\n"
        "ID do seu depósito: `" + pid + "`"
    )
    await update.message.reply_text(msg_final, parse_mode=ParseMode.MARKDOWN)
    ctx.user_data.clear()

# 5. APROVAÇÃO UNIVERSAL (DEPÓSITOS E SAQUES)
async def aprovar_recusar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acao, pid = query.data.split("|")
    
    pendentes = carregar_json(PENDENTES_FILE)
    if pid not in pendentes: return await query.edit_message_text("❌ Pedido expirado ou já processado.")
    
    pedido = pendentes.pop(pid)
    uid, valor, tipo = pedido["user_id"], pedido["valor"], pedido.get("tipo", "deposito")
    usuarios = carregar_json(USERS_FILE)
    
    if acao == "aprovar":
        if tipo == "deposito":
            usuarios[uid]["saldo"] += valor
            msg_user = (
                "🎉 **PARABÉNS! DEPÓSITO APROVADO!**\n\n"
                f"O valor de {fmt(valor)} caiu na sua conta! ✅\n\n"
                "🚀 **PRÓXIMO PASSO:**\n"
                "Vá em **Ver Planos** e comece a investir para gerar lucros diários!"
            )
        else: # Se for saque
            msg_user = f"✅ **SAQUE APROVADO!**\nSeu levantamento de {fmt(valor)} foi enviado com sucesso!"
            
        salvar_json(USERS_FILE, usuarios)
        await ctx.bot.send_message(uid, msg_user, parse_mode=ParseMode.MARKDOWN)
        await query.edit_message_caption(caption=f"✅ {tipo.upper()} APROVADO!")

    else:
        if tipo == "deposito":
            msg_user = "❌ *DEPÓSITO RECUSADO*\nSua solicitação foi negada. Verifique o comprovante ou fale com o suporte."
        else: # Se recusar saque, devolve o saldo
            usuarios[uid]["saldo"] += valor
            salvar_json(USERS_FILE, usuarios)
            msg_user = "❌ *SAQUE RECUSADO*\nSeu pedido foi negado e o saldo devolvido à conta."
            
        await ctx.bot.send_message(uid, msg_user, parse_mode=ParseMode.MARKDOWN)
        await query.edit_message_caption(caption=f"❌ {tipo.upper()} RECUSADO.")
    
    salvar_json(PENDENTES_FILE, pendentes)

async def enviar_relatorio_diario(application):
    """
    Função que gera estatísticas completas e envia ao administrador.
    """
    usuarios = carregar_json(USERS_FILE)
    hoje = datetime.now().strftime("%d/%m/%Y")
    
    total_users = len(usuarios)
    novos_hoje = 0
    saldo_total_mzn = 0
    dep_hoje_mzn = 0
    saq_hoje_mzn = 0
    planos_ativos = 0

    # Percorre todos os usuários para somar os dados
    for uid, u in usuarios.items():
        # Conta novos cadastros
        if u.get("data_cadastro") == hoje or u.get("data_criacao") == hoje:
            novos_hoje += 1
        
        # Soma saldos e planos
        saldo_total_mzn += u.get("saldo", 0)
        planos_ativos += len(u.get("planos", []))

        # Analisa o histórico de transações do dia
        historico = u.get("historico", [])
        if isinstance(historico, list):
            for item in historico:
                data_item = item.get("data", "")
                if hoje in data_item and item.get("status") == "aprovado":
                    valor = float(item.get("valor", 0))
                    if item.get("tipo") == "deposito":
                        dep_hoje_mzn += valor
                    elif item.get("tipo") == "saque":
                        saq_hoje_mzn += valor

    # Formatação de Moeda (USD/MZN)
    def f_dual(mzn):
        usd = mzn / 70 # Taxa de câmbio
        return f"{usd:.2f} USD (~{mzn:.2f} MZN)"

    # Montagem da Mensagem
    msg = (
        f"📊 *RELATÓRIO DIÁRIO - {NOME_BOT}*\n"
        f"📅 Data: {hoje}\n\n"
        f"👥 *Usuários:*\n"
        f"• Novos hoje: {novos_hoje}\n"
        f"• Total cadastrados: {total_users}\n\n"
        f"💰 *Estatísticas do Site:*\n"
        f"• Saldo total em contas: {f_dual(saldo_total_mzn)}\n"
        f"• Total de planos ativos: {planos_ativos}\n\n"
        f"📥 *Movimentação de Hoje (Aprovados):*\n"
        f"• Total Depósitos: {f_dual(dep_hoje_mzn)}\n"
        f"• Total Saques: {f_dual(saq_hoje_mzn)}\n\n"
        f"✅ Sistema DualWave operacional."
    )
    
    try:
        await application.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"Erro ao enviar relatório: {e}")

# ✅ FUNÇÃO PARA INICIAR O SCHEDULER DENTRO DO LOOP DO BOT
async def post_init(application):
    """
    Esta função roda automaticamente assim que o bot inicia o loop de eventos.
    Isso evita o erro 'no running event loop'.
    """
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    # Agendar o relatório para as 16:27 UTC (Ajuste a hora se necessário)
    scheduler.add_job(enviar_relatorio_diario, 'cron', hour=16, minute=27, args=[application])
    scheduler.start()
    print("⏰ Agendador de relatórios iniciado com sucesso!")

# ✅ FUNÇÃO PRINCIPAL DE INICIALIZAÇÃO
def main():
    # Criamos o app e adicionamos o '.post_init(post_init)'
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # 1. Registro de Comandos e Callbacks
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(set_lang, pattern="^setlang\\|"))
    #app.add_handler(CallbackQueryHandler(ajuda_start_cb, pattern="^ajuda_start$"))
    app.add_handler(CallbackQueryHandler(ajuda_saldo_cb, pattern="^ajuda_saldo$"))
    app.add_handler(CallbackQueryHandler(ajuda_depositar_cb, pattern="^ajuda_depositar$"))
    app.add_handler(CallbackQueryHandler(dep_metodo_cb, pattern="^dep_metodo\\|"))
    app.add_handler(CallbackQueryHandler(aprovar_recusar, pattern="^(aprovar|recusar)\\|"))
    #app.add_handler(CallbackQueryHandler(ajuda_coletar_cb, pattern="^ajuda_coletar$"))
    #app.add_handler(CallbackQueryHandler(ajuda_indicacao_cb, pattern="^ajuda_indicacao$"))

    # 2. Registro de Mensagens (Texto e Fotos)
    app.add_handler(MessageHandler(filters.PHOTO, tratar_comprovante))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_mensagens_deposito))

    print("🚀 DualWave Bot Iniciado e Rodando!")
    
    # Inicia o bot (O run_polling cuida de tudo agora)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
