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
    uid = str(query.from_user.id)
    usuarios = carregar_json(USERS_FILE)
    user = usuarios.get(uid)
    lang = user.get("lang", "pt")
    
    # Limpeza visual
    try: await query.message.delete()
    except: pass

    saldo_mzn = user.get("saldo", 0)
    
    # Texto do Saldo
    titulo = "💰 *MEU SALDO / MY BALANCE*"
    msg = (
        f"{titulo}\n\n"
        f"💵 *Disponível:* `{fmt(saldo_mzn)}`\n"
        f"📊 *Planos Ativos:* {len(user.get('planos', []))}\n\n"
        "Selecione uma opção abaixo:"
    )
    
    # Botões organizados: Depósito e Saque na mesma linha, Configurações embaixo.
    kb = [
        [
            InlineKeyboardButton("📥 Depósito", callback_data="ajuda_depositar"),
            InlineKeyboardButton("📤 Saque", callback_data="ajuda_sacar") # <- LIGADO À FUNÇÃO DE SAQUE
        ],
        [InlineKeyboardButton("⚙️ Configurar Dados de Saque", callback_data="config_saque_menu")],
        [InlineKeyboardButton("⬅️ Voltar / Back", callback_data="ajuda_start")]
    ]
    
    await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

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
            await tratar_mensagens_saque(update, ctx)

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

# ==========================================
# 📤 SISTEMA DE SAQUE E CONFIGURAÇÕES BANCÁRIAS
# ==========================================

# --- 1. MENU DE CONFIGURAÇÃO DE SAQUE (MÉTODO E PIN) ---
async def config_saque_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    user = carregar_json(USERS_FILE).get(uid)
    
    try: await query.message.delete()
    except: pass

    pin_status = "✅ Definido" if user.get("saque_pin") else "❌ Não definido"
    metodo = user.get("saque_metodo", "Não configurado")
    
    msg = (
        "⚙️ *CONFIGURAÇÕES DE LEVANTAMENTO*\n\n"
        f"🔒 *PIN de Saque:* {pin_status}\n"
        f"💳 *Método Atual:* {metodo}\n"
        f"📱 *Número:* {user.get('saque_numero', '---')}\n"
        f"👤 *Titular:* {user.get('saque_titular', '---')}\n\n"
        "Seus dados devem estar corretos para evitar falhas no pagamento."
    )
    
    kb = [
        [InlineKeyboardButton("🔐 Alterar/Definir PIN", callback_data="config_saque_pin")],
        [InlineKeyboardButton("💳 Alterar Dados Bancários", callback_data="config_saque_dados")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="ajuda_saldo")]
    ]
    await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- 2. INÍCIO DO PROCESSO DE SAQUE (VERIFICAÇÕES DE TRAVA) ---
async def ajuda_sacar_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    user = carregar_json(USERS_FILE).get(uid)

    # Verificação se o PIN e Dados existem ANTES de continuar
    if not user.get("saque_pin") or not user.get("saque_metodo"):
        return await query.message.reply_text(
            "⚠️ *Atenção:* Você ainda não configurou seus dados de saque!\n\n"
            "Por favor, vá em *Meu Saldo* -> *Configurar Dados de Saque* antes de tentar retirar valores.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # A. Verificação de Horário (Seg-Sex, 10:30 - 18:30)
    agora = datetime.now()
    hora_atual = agora.time()
    inicio_saque = datetime.strptime("10:30", "%H:%M").time()
    fim_saque = datetime.strptime("18:30", "%H:%M").time()
    
    if agora.weekday() >= 5: # 5 = Sábado, 6 = Domingo
        return await query.answer("❌ Saques disponíveis apenas de Segunda a Sexta-feira.", show_alert=True)
    
    if not (inicio_saque <= hora_atual <= fim_saque):
        return await query.answer(f"🕒 Horário de saque: 10:30h às 18:30h.\nAgora são: {agora.strftime('%H:%M')}h", show_alert=True)

    # B. Verificação de Depósito Mínimo
    if user.get("deposito_total", 0) <= 0:
        return await query.answer("❌ Você precisa fazer um depósito antes de realizar saques.", show_alert=True)

    # C. Verificação de Plano (Ativo ou Expirado há menos de 5 dias)
    tem_plano_recente = False
    # Checa ativos
    if any(p.get("status") == "ativo" for p in user.get("planos", [])):
        tem_plano_recente = True
    else:
        # Checa expirados
        for p in user.get("planos_expirados", []):
            try:
                data_exp = datetime.strptime(p.get("data_expiracao"), "%d/%m/%Y")
                if (agora - data_exp).days <= 5:
                    tem_plano_recente = True
                    break
            except: continue

    if not tem_plano_recente:
        return await query.answer("❌ Você precisa ter um plano ativo (ou que expirou nos últimos 5 dias).", show_alert=True)

    # D. Verificação de Dados Bancários
    if not user.get("saque_metodo") or not user.get("saque_pin"):
        return await query.answer("⚠️ Configure seu PIN e dados bancários primeiro!", show_alert=True)

    # Tudo OK, pede o valor
    try: await query.message.delete()
    except: pass
    
    ctx.user_data["esperando_val_saque"] = True
    await query.message.reply_text(
        "📤 *SOLICITAÇÃO DE SAQUE*\n\n"
        f"💰 Saldo Disponível: {fmt(user['saldo'])}\n"
        "Digite o valor que deseja sacar (MZN):", 
        parse_mode=ParseMode.MARKDOWN
    )

# --- 3. PROCESSAMENTO DO TEXTO (VALOR E PIN) ---
# Adicione isso na sua função 'tratar_mensagens'
async def tratar_mensagens_saque(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text
    usuarios = carregar_json(USERS_FILE)
    user = usuarios[uid]

    # PASSO A: RECEBER VALOR
    if ctx.user_data.get("esperando_val_saque"):
        try:
            valor = float(text)
            if valor < 150: # Mínimo saque sugerido
                return await update.message.reply_text("❌ Valor mínimo para saque é 150 MZN.")
            if valor > user["saldo"]:
                return await update.message.reply_text("❌ Saldo insuficiente.")
            
            taxa = valor * 0.13
            receber = valor - taxa
            ctx.user_data["saque_valor"] = valor
            ctx.user_data["saque_receber"] = receber
            ctx.user_data["esperando_val_saque"] = False
            ctx.user_data["esperando_pin_saque"] = True
            
            msg = (
                "📝 *RESUMO DO SAQUE*\n\n"
                f"💵 Valor solicitado: {fmt(valor)}\n"
                f"💸 Taxa (13%): {fmt(taxa)}\n"
                f"✅ *Valor Líquido:* {fmt(receber)}\n\n"
                "🔒 *Digite seu PIN de Saque para confirmar:* "
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        except:
            await update.message.reply_text("❌ Digite um valor numérico válido.")

    # PASSO B: RECEBER PIN E FINALIZAR
    elif ctx.user_data.get("esperando_pin_saque"):
        if text != str(user.get("saque_pin")):
            return await update.message.reply_text("❌ PIN Incorreto! Tente novamente ou cancele.")
        
        # Cria o pedido de saque
        valor = ctx.user_data["saque_valor"]
        pid = gerar_id()
        
        # Subtrai do saldo
        user["saldo"] -= valor
        salvar_json(USERS_FILE, usuarios)
        
        # Salva nos pendentes para o Admin
        pendentes = carregar_json(PENDENTES_FILE)
        pendentes[pid] = {
            "user_id": uid, "valor": valor, "receber": ctx.user_data["saque_receber"],
            "tipo": "saque", "metodo": user['saque_metodo'], 
            "numero": user['saque_numero'], "titular": user['saque_titular']
        }
        salvar_json(PENDENTES_FILE, pendentes)
        
        # Notifica Admin
        caption_admin = (
            "📤 *PEDIDO DE SAQUE*\n\n"
            f"👤 Usuário: {user['nome']}\n"
            f"💵 Valor Bruto: {fmt(valor)}\n"
            f"💸 Valor Líquido: {fmt(ctx.user_data['saque_receber'])}\n"
            f"🏛️ Método: {user['saque_metodo']}\n"
            f"📱 Número: `{user['saque_numero']}`\n"
            f"👤 Titular: {user['saque_titular']}\n"
            f"🆔 ID: `{pid}`"
        )
        await ctx.bot.send_message(ADMIN_ID, caption_admin, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aprovar Saque", callback_data=f"aprovar|{pid}"),
            InlineKeyboardButton("❌ Recusar Saque", callback_data=f"recusar|{pid}")
        ]]))

        await update.message.reply_text("🚀 *Saque enviado com sucesso!*\nAguarde o processamento financeiro.")
        ctx.user_data.clear()

    # PASSO C: DEFINIR DADOS BANCÁRIOS
    elif ctx.user_data.get("esperando_dados_bancarios"):
        # Exemplo de entrada: M-Pesa, 84xxxxxx, Nome Silva
        try:
            partes = text.split(",")
            user["saque_metodo"] = partes[0].strip()
            user["saque_numero"] = partes[1].strip()
            user["saque_titular"] = partes[2].strip()
            salvar_json(USERS_FILE, usuarios)
            ctx.user_data["esperando_dados_bancarios"] = False
            await update.message.reply_text("✅ Dados bancários salvos com sucesso!")
        except:
            await update.message.reply_text("❌ Formato inválido. Use: Metodo, Numero, Nome")

    # PASSO D: DEFINIR PIN
    elif ctx.user_data.get("esperando_novo_pin"):
        if len(text) < 4:
            return await update.message.reply_text("❌ O PIN deve ter no mínimo 4 dígitos.")
        user["saque_pin"] = text
        salvar_json(USERS_FILE, usuarios)
        ctx.user_data["esperando_novo_pin"] = False
        await update.message.reply_text("✅ Seu PIN de segurança foi salvo!")

# 5. APROVAÇÃO UNIVERSAL (DEPÓSITOS E SAQUES)
async def aprovar_recusar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Extrai ação e ID do pedido
    try:
        acao, pid = query.data.split("|")
    except:
        return await query.edit_message_text("❌ Erro nos dados do callback.")
    
    pendentes = carregar_json(PENDENTES_FILE)
    if pid not in pendentes: 
        return await query.edit_message_text("❌ Pedido expirado ou já processado.")
    
    pedido = pendentes.pop(pid)
    uid = pedido["user_id"]
    valor = pedido["valor"]
    tipo = pedido.get("tipo", "deposito")
    
    usuarios = carregar_json(USERS_FILE)
    if uid not in usuarios:
        return await query.edit_message_text("❌ Usuário não encontrado no banco de dados.")

    if acao == "aprovar":
        if tipo == "deposito":
            # 1. Atualiza Saldo e Total Depositado do Usuário
            usuarios[uid]["saldo"] += valor
            usuarios[uid]["deposito_total"] = usuarios[uid].get("deposito_total", 0) + valor
            
            # Registro no Histórico
            usuarios[uid].setdefault("historico", []).append({
                "tipo": "deposito", "valor": valor, "status": "aprovado", 
                "data": datetime.now().strftime("%d/%m/%Y %H:%M")
            })

            # 2. LÓGICA DE COMISSÕES (Nível 1 e 2)
            percentuais = {1: 0.07, 2: 0.03} # 7% e 3%
            usuario_atual = usuarios[uid]

            for nivel in range(1, 3):
                pai_id = usuario_atual.get("indicador")
                if not pai_id or pai_id not in usuarios: 
                    break

                pai = usuarios[pai_id]
                comissao = valor * percentuais[nivel]
                
                # VERIFICAÇÃO DE PLANO ATIVO PARA RECEBER
                # Verifica se existe algum plano com status "ativo"
                tem_plano = any(p.get("status") == "ativo" for p in pai.get("planos", []))
                
                if tem_plano:
                    pai["saldo"] += comissao
                    log_msg = f"✅ *Bônus de Equipe!*\nVocê recebeu {fmt(comissao)} (Nível {nivel}) pelo depósito de um convidado!"
                else:
                    log_msg = f"⚠️ *Aviso de Comissão:*\nUm convidado seu depositou {fmt(valor)}, mas você PERDEU a comissão de {fmt(comissao)} porque NÃO tem um plano ativo!"

                # Registra estatística de comissão (mesmo que não ganhe o saldo, para o menu Equipe)
                if "comissoes" not in pai: pai["comissoes"] = {"1": 0, "2": 0}
                pai["comissoes"][str(nivel)] = pai["comissoes"].get(str(nivel), 0) + comissao
                
                # Notifica o patrocinador (pai/avô)
                try: await ctx.bot.send_message(chat_id=int(pai_id), text=log_msg, parse_mode=ParseMode.MARKDOWN)
                except: pass
                
                usuario_atual = pai # Sobe para o próximo nível

            msg_user = (
                "🎉 *PARABÉNS! DEPÓSITO APROVADO!*\n\n"
                f"O valor de {fmt(valor)} foi creditado! ✅\n\n"
                "🚀 *PRÓXIMO PASSO:*\n"
                "Vá em *Ver Planos* e comece a investir para gerar lucros diários!"
            )
        
        else: # Lógica para SAQUE
            msg_user = f"✅ *SAQUE APROVADO!*\nSeu levantamento de {fmt(valor)} foi processado e enviado!"

        await ctx.bot.send_message(uid, msg_user, parse_mode=ParseMode.MARKDOWN)
        await query.edit_message_caption(caption=f"✅ {tipo.upper()} APROVADO COM SUCESSO!")

    else: # AÇÃO: RECUSAR
        if tipo == "deposito":
            msg_user = "❌ *DEPÓSITO RECUSADO*\nSua solicitação foi negada. Verifique se o comprovante é real ou fale com o suporte."
        else:
            # Se recusar saque, devolve o dinheiro para o saldo do usuário
            usuarios[uid]["saldo"] += valor
            msg_user = "❌ *SAQUE RECUSADO*\nSeu pedido foi negado e o valor foi devolvido ao seu saldo."

        await ctx.bot.send_message(uid, msg_user, parse_mode=ParseMode.MARKDOWN)
        await query.edit_message_caption(caption=f"❌ {tipo.upper()} RECUSADO.")

    # Salva todas as alterações nos arquivos
    salvar_json(USERS_FILE, usuarios)
    salvar_json(PENDENTES_FILE, pendentes)

# ==========================================
# 👥 SISTEMA DE EQUIPE E INDICAÇÃO
# ==========================================
async def ajuda_indicacao_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    usuarios = carregar_json(USERS_FILE)
    user = usuarios.get(uid)

    # CORREÇÃO 1: Verifica se o usuário existe no banco
    if not user:
        return await query.message.reply_text("❌ Erro: Seu perfil não foi encontrado. Digite /start")

    # Limpeza de tela
    try: await query.message.delete()
    except: pass

    # CORREÇÃO 2: Lógica de Nível 1 e 2 sem depender da chave "user_id" interna
    # Buscamos diretamente pelos IDs (chaves) do dicionário usuarios
    
    # IDs de quem você convidou diretamente (Nível 1)
    ids_n1 = [id_u for id_u, dados in usuarios.items() if dados.get("indicador") == uid]
    indicados_n1 = [usuarios[id_u] for id_u in ids_n1]
    
    # Dados de quem os seus amigos convidaram (Nível 2)
    indicados_n2 = [dados for id_u, dados in usuarios.items() if dados.get("indicador") in ids_n1]

    # Contagem de Ativos (quem já depositou algo)
    ativos_n1 = sum(1 for u in indicados_n1 if u.get("deposito_total", 0) > 0)
    ativos_n2 = sum(1 for u in indicados_n2 if u.get("deposito_total", 0) > 0)
    total_ativos = ativos_n1 + ativos_n2

    # Comissões (Uso do .get para evitar erros se a chave não existir)
    comissoes_data = user.get("comissoes", {})
    # Garante que tratamos como string, pois JSON salva chaves como string
    com_n1 = comissoes_data.get("1", 0)
    com_n2 = comissoes_data.get("2", 0)
    total_ganho = com_n1 + com_n2

    link = f"https://t.me/{ctx.bot.username}?start={uid}"
    
    msg = (
        f"👥 *MINHA EQUIPE - DUALWAVE*\n\n"
        f"🔗 *Seu Link:* `{link}`\n\n"
        f"📊 *Estatísticas:* \n"
        f"• Total Convidados: {len(indicados_n1) + len(indicados_n2)}\n"
        f"• Convidados Ativos: {total_ativos}\n\n"
        f"🥇 *Nível 1:* {len(indicados_n1)} usuários ({ativos_n1} ativos)\n"
        f"💰 Ganho Nível 1: {fmt(com_n1)}\n\n"
        f"🥈 *Nível 2:* {len(indicados_n2)} usuários ({ativos_n2} ativos)\n"
        f"💰 Ganho Nível 2: {fmt(com_n2)}\n\n"
        f"💵 *TOTAL GANHO:* {fmt(total_ganho)}\n"
        f"________________________________\n"
        f"⚠️ _Lembre-se: Você só recebe comissões se tiver um Plano Ativo!_"
    )

    kb = [
        [InlineKeyboardButton("🚀 Compartilhar Link", url=f"https://t.me/share/url?url={link}&text=Ganhe%20dinheiro%20diariamente%20na%20DualWave!")],
        [InlineKeyboardButton("🏆 Campanhas / Prêmios", callback_data="equipe_campanhas")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="ajuda_start")]
    ]
    await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def equipe_campanhas_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    usuarios = carregar_json(USERS_FILE)
    user = usuarios.get(uid)

    # Contar ativos nível 1 (para as metas)
    indicados_n1 = [u for u in usuarios.values() if u.get("indicador") == uid]
    ativos = sum(1 for u in indicados_n1 if u.get("deposito_total", 0) > 0)
    
    # Lista de prêmios já resgatados
    resgatados = user.get("campanhas_ganhas", [])

    msg = (
        f"🏆 *CAMPANHAS DUALWAVE*\n\n"
        f"Convide amigos ativos (que depositam) e ganhe prêmios!\n"
        f"Seus ativos atuais: *{ativos}*\n\n"
        f"1️⃣ *Meta 10 Ativos:* 155 MZN\n"
        f"2️⃣ *Meta 25 Ativos:* 550 MZN\n"
        f"3️⃣ *Meta 50 Ativos:* +1 Plano Wave Starter (350 MZN)\n"
        f"4️⃣ *Meta 100 Ativos:* 10.000 MZN\n"
    )

    kb = []
    # Lógica de botões de resgate
    metas = [(10, 155, "m1"), (25, 550, "m2"), (50, "PLANO", "m3"), (100, 10000, "m4")]
    
    for meta, premio, cod in metas:
        if cod in resgatados:
            kb.append([InlineKeyboardButton(f"✅ Meta {meta} - Resgatado", callback_data="null")])
        elif ativos >= meta:
            kb.append([InlineKeyboardButton(f"🎁 RESGATAR META {meta}", callback_data=f"resgatar|{cod}")])
        else:
            kb.append([InlineKeyboardButton(f"🔒 Meta {meta} ({ativos}/{meta})", callback_data="null")])

    kb.append([InlineKeyboardButton("⬅️ Voltar", callback_data="ajuda_indicacao")])
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def resgatar_campanha_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cod = query.data.split("|")[1]
    uid = str(query.from_user.id)
    usuarios = carregar_json(USERS_FILE)
    user = usuarios[uid]

    if "campanhas_ganhas" not in user: user["campanhas_ganhas"] = []
    
    premios = {
        "m1": (155, "dinheiro"),
        "m2": (550, "dinheiro"),
        "m3": (350, "plano"),
        "m4": (10000, "dinheiro")
    }

    valor, tipo = premios[cod]
    user["campanhas_ganhas"].append(cod)

    if tipo == "dinheiro":
        user["saldo"] += valor
        msg = f"🎉 Parabéns! Você resgatou seu prêmio de {fmt(valor)}!"
    else:
        # Dar o primeiro plano gratuitamente
        novo_plano = {"nome": "Wave Starter", "valor": 350, "percent": 0.07, "dias": 25, "status": "ativo"}
        user["planos"].append(novo_plano)
        msg = "🎉 Incrível! Você ganhou um Plano Wave Starter ativo!"

    salvar_json(USERS_FILE, usuarios)
    await query.edit_message_text(msg)

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
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # --- HANDLERS DO MENU PRINCIPAL E SALDO ---
    app.add_handler(CommandHandler("start", start))
    #app.add_handler(CallbackQueryHandler(ajuda_start_cb, pattern="^ajuda_start$"))
    app.add_handler(CallbackQueryHandler(ajuda_saldo_cb, pattern="^ajuda_saldo$"))

    # --- HANDLERS DE DEPÓSITO ---
    app.add_handler(CallbackQueryHandler(ajuda_depositar_cb, pattern="^ajuda_depositar$"))
    app.add_handler(CallbackQueryHandler(dep_metodo_cb, pattern="^dep_metodo\\|"))

    # --- HANDLERS DE SAQUE E CONFIGURAÇÃO (O QUE ESTAVA FALTANDO) ---
    app.add_handler(CallbackQueryHandler(ajuda_sacar_cb, pattern="^ajuda_sacar$")) # <- FAZ O BOTÃO SAQUE RESPONDER
    app.add_handler(CallbackQueryHandler(config_saque_menu_cb, pattern="^config_saque_menu$")) # <- FAZ O BOTÃO CONFIG RESPONDER
    app.add_handler(CallbackQueryHandler(config_saque_pin_cb, pattern="^config_saque_pin$")) # Função de PIN
    app.add_handler(CallbackQueryHandler(config_saque_dados_cb, pattern="^config_saque_dados$")) # Função de Dados

    # --- APROVAÇÃO ADMIN ---
    app.add_handler(CallbackQueryHandler(aprovar_recusar, pattern="^(aprovar|recusar)\\|"))

    # --- MENSAGENS DE TEXTO (VALOR E PIN) ---
    app.add_handler(MessageHandler(filters.PHOTO, tratar_comprovante))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_mensagens_deposito))

    app.run_polling(drop_pending_updates=True)
    
if __name__ == "__main__":
    main()
