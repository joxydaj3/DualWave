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

    # Limpeza de tela
    try: await query.message.delete()
    except: pass

    # Cálculos de Nível 1 e 2
    indicados_n1 = [u for u in usuarios.values() if u.get("indicador") == uid]
    indicados_n2 = []
    for n1 in indicados_n1:
        n2_list = [u for u in usuarios.values() if u.get("indicador") == n1["user_id"]]
        indicados_n2.extend(n2_list)

    # Contagem de Ativos (quem já depositou)
    ativos_n1 = sum(1 for u in indicados_n1 if u.get("deposito_total", 0) > 0)
    ativos_n2 = sum(1 for u in indicados_n2 if u.get("deposito_total", 0) > 0)
    total_ativos = ativos_n1 + ativos_n2

    # Comissões
    com_n1 = user.get("comissoes", {}).get("1", 0)
    com_n2 = user.get("comissoes", {}).get("2", 0)
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
    # Handlers para o Sistema de Equipe e Campanhas
    app.add_handler(CallbackQueryHandler(ajuda_indicacao_cb, pattern="^ajuda_indicacao$"))
    app.add_handler(CallbackQueryHandler(equipe_campanhas_cb, pattern="^equipe_campanhas$"))
    app.add_handler(CallbackQueryHandler(resgatar_campanha_cb, pattern="^resgatar\\|"))

    # 2. Registro de Mensagens (Texto e Fotos)
    app.add_handler(MessageHandler(filters.PHOTO, tratar_comprovante))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tratar_mensagens_deposito))

    print("🚀 DualWave Bot Iniciado e Rodando!")
    
    # Inicia o bot (O run_polling cuida de tudo agora)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
