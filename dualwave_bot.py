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
        f"💰 *{TEXTOS[lang]['btn_saldo']}*\n\n"
        f"💵 *Total:* `{fmt(saldo_mzn)}`\n"
        f"📊 Planos Ativos: {len(user.get('planos', []))}\n"
    )
    
    buttons = [
        [InlineKeyboardButton("📥 Depósito", callback_data="ajuda_depositar"), InlineKeyboardButton("📤 Saque", callback_data="ajuda_sacar")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="ajuda_start")]
    ]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

# ✅ DEPÓSITO (ADAPTADO)
async def ajuda_depositar_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    kb = [
        [InlineKeyboardButton("M-Pesa 🇲🇿", callback_data="dep_metodo|M-Pesa")],
        [InlineKeyboardButton("E-Mola 🇲🇿", callback_data="dep_metodo|E-Mola")],
        [InlineKeyboardButton("USDT (BEP20) 🌐", callback_data="dep_metodo|Crypto")]
    ]
    await query.edit_message_text("💵 Escolha o método de depósito:", reply_markup=InlineKeyboardMarkup(kb))

async def dep_metodo_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    metodo = query.data.split("|")[1]
    ctx.user_data["dep_mtd"] = metodo
    
    contas = {
        "M-Pesa": "849564273",
        "E-Mola": "877329951",
        "Crypto": "0x0df8e7b0c172f509f6aff2791fb500462b13a5e5 (BEP20)"
    }
    
    msg = f"✅ Método: *{metodo}*\nTransferir para: `{contas[metodo]}`\n\n*Digite o valor em MZN (Min: 350):*"
    ctx.user_data["esperando_val_dep"] = True
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)

# ✅ TRATAMENTO DE TEXTOS E VALORES
async def tratar_mensagens(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text
    usuarios = carregar_json(USERS_FILE)
    
    if ctx.user_data.get("esperando_val_dep"):
        try:
            valor = float(text)
            if valor < 350: raise ValueError
            ctx.user_data["dep_val"] = valor
            ctx.user_data["esperando_val_dep"] = False
            ctx.user_data["esperando_img_dep"] = True
            await update.message.reply_text("📸 Agora envie o *comprovante (foto)*.")
        except:
            await update.message.reply_text("❌ Valor inválido. Mínimo 350 MZN.")
            
    elif ctx.user_data.get("esperando_val_saque"):
        # Lógica de saque similar ao seu arquivo
        pass

async def tratar_comprovante(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.user_data.get("esperando_img_dep"): return
    
    photo = update.message.photo[-1].file_id
    pid = gerar_id()
    uid = str(update.effective_user.id)
    
    pendentes = carregar_json(PENDENTES_FILE)
    pendentes[pid] = {
        "user_id": uid,
        "valor": ctx.user_data["dep_val"],
        "mtd": ctx.user_data["dep_mtd"],
        "status": "pendente"
    }
    salvar_json(PENDENTES_FILE, pendentes)
    
    # Notificar Admin
    await ctx.bot.send_photo(
        ADMIN_ID, 
        photo=photo, 
        caption=f"💰 *Novo Depósito DualWave*\nID: {pid}\nValor: {ctx.user_data['dep_val']} MZN\nUser: {uid}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar|{pid}"),
            InlineKeyboardButton("❌ Recusar", callback_data=f"recusar|{pid}")
        ]])
    )
    await update.message.reply_text("✅ Comprovante enviado! Aguarde a aprovação.")
    ctx.user_data.clear()

# ✅ PROCESSAR APROVAÇÃO
async def aprovar_recusar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acao, pid = query.data.split("|")
    
    pendentes = carregar_json(PENDENTES_FILE)
    if pid not in pendentes: return await query.edit_message_text("❌ Já processado.")
    
    pedido = pendentes.pop(pid)
    uid = pedido["user_id"]
    usuarios = carregar_json(USERS_FILE)
    
    if acao == "aprovar":
        usuarios[uid]["saldo"] += pedido["valor"]
        salvar_json(USERS_FILE, usuarios)
        await ctx.bot.send_message(uid, f"✅ Seu depósito de {fmt(pedido['valor'])} foi aprovado!")
        await query.edit_message_caption(caption="✅ Aprovado com sucesso!")
    else:
        await ctx.bot.send_message(uid, "❌ Seu depósito foi recusado.")
        await query.edit_message_caption(caption="❌ Recusado.")
    
    salvar_json(PENDENTES_FILE, pendentes)

# ✅ FUNÇÃO PRINCIPAL DE INICIALIZAÇÃO
def main():
    # Cria a aplicação
    app = ApplicationBuilder().token(TOKEN).build()

    # 1. Registro de Comandos e Callbacks
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(set_lang, pattern="^setlang\\|"))
    app.add_handler(CallbackQueryHandler(ajuda_saldo_cb, pattern="^ajuda_saldo$"))
    app.add_handler(CallbackQueryHandler(ajuda_depositar_cb, pattern="^ajuda_depositar$"))
    app.add_handler(CallbackQueryHandler(dep_metodo_cb, pattern="^dep_metodo\\|"))
    app.add_handler(CallbackQueryHandler(aprovar_recusar, pattern="^(aprovar|recusar)\\|"))
    
    # 2. Registro de Mensagens (Texto e Fotos)
    app.add_handler(MessageHandler(filters.PHOTO, tratar_comprovante))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_mensagens))

    # 3. Configuração do Relatório Diário (Scheduler)
    # O PTB v20+ já integra o JobQueue, mas como você usa o APScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.start()

    print("🚀 DualWave Bot Iniciado e Rodando!")
    
    # O run_polling() aqui NÃO deve ter 'await' e NÃO deve estar dentro de 'asyncio.run'
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
