import discord
from discord.ext import commands, tasks
import json
import os
import asyncio

# --- CONFIGURATION DES INTENTS ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- GESTION DE LA BASE DE DONNÉES (JSON) ---
DB_FILE = "database.json"

def load_data():
    if not os.path.exists(DB_FILE):
        return {
            "teams": {},
            "users": {}
        }
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Anti-spam d'XP texte (1 fois par minute max)
cooldowns = {}

# --- ÉVÉNEMENTS ---

@bot.event
async def on_ready():
    print(f"✅ Bot connecté avec succès en tant que {bot.user.name} !")
    if not xp_vocal_loop.is_running():
        xp_vocal_loop.start()

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    user_id = str(message.author.id)
    now = asyncio.get_event_loop().time()

    # Anti-spam : 1 gain d'XP max toutes les 60 secondes par message
    if user_id in cooldowns and now - cooldowns[user_id] < 60:
        await bot.process_commands(message)
        return

    data = load_data()
    user_roles = [r.id for r in message.author.roles]

    target_team_key = None
    for team_key, team_info in data["teams"].items():
        if team_info.get("role_id") in user_roles:
            target_team_key = team_key
            break

    if target_team_key:
        cooldowns[user_id] = now
        
        if user_id not in data["users"]:
            data["users"][user_id] = {"xp": 0, "team_key": target_team_key}

        # 10 XP par message
        data["users"][user_id]["xp"] += 10
        data["users"][user_id]["team_key"] = target_team_key
        data["teams"][target_team_key]["xp"] += 10
        save_data(data)

    await bot.process_commands(message)

# --- BOUCLE XP VOCAL (Toutes les minutes) ---

@tasks.loop(minutes=1)
async def xp_vocal_loop():
    data = load_data()
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            for member in channel.members:
                if member.bot or (member.voice and member.voice.self_deaf):
                    continue

                user_roles = [r.id for r in member.roles]
                target_team_key = None
                for team_key, team_info in data["teams"].items():
                    if team_info.get("role_id") in user_roles:
                        target_team_key = team_key
                        break

                if target_team_key:
                    user_id = str(member.id)
                    if user_id not in data["users"]:
                        data["users"][user_id] = {"xp": 0, "team_key": target_team_key}

                    # 5 XP par minute en vocal
                    data["users"][user_id]["xp"] += 5
                    data["users"][user_id]["team_key"] = target_team_key
                    data["teams"][target_team_key]["xp"] += 5

    save_data(data)

# --- COMMANDES D'ADMINISTRATION ---

@bot.command()
@commands.has_permissions(administrator=True)
async def setteam(ctx, identifiant: str, role: discord.Role, *, nom_equipe: str):
    data = load_data()
    data["teams"][identifiant] = {"name": nom_equipe, "role_id": role.id, "xp": 0}
    save_data(data)
    await ctx.send(f"✅ Équipe configurée : **{nom_equipe}** (ID: `{identifiant}`) associée au rôle {role.mention}.")

@bot.command()
@commands.has_permissions(administrator=True)
async def renameteam(ctx, identifiant: str, *, nouveau_nom: str):
    data = load_data()
    if identifiant not in data["teams"]:
        await ctx.send(f"❌ Aucune équipe trouvée avec l'identifiant `{identifiant}`.")
        return
    ancien_nom = data["teams"][identifiant]["name"]
    data["teams"][identifiant]["name"] = nouveau_nom
    save_data(data)
    await ctx.send(f"✏️ L'équipe **{ancien_nom}** a été renommée en **{nouveau_nom}** !")

@bot.command()
@commands.has_permissions(administrator=True)
async def resetscores(ctx):
    data = load_data()
    for t in data["teams"]:
        data["teams"][t]["xp"] = 0
    data["users"] = {}
    save_data(data)
    await ctx.send("🔄 Tous les scores et XP ont été réinitialisés !")

# --- COMMANDES JOUEURS ---

@bot.command()
async def score(ctx):
    data = load_data()
    if not data["teams"]:
        await ctx.send("❌ Aucune équipe n'est configurée. Un admin doit exécuter `!setteam`.")
        return

    embed = discord.Embed(
        title="⚔️ DUEL D'XP DES ÉQUIPES",
        description="Classement général du serveur :",
        color=discord.Color.gold()
    )

    sorted_teams = sorted(data["teams"].items(), key=lambda x: x[1]["xp"], reverse=True)

    for key, info in sorted_teams:
        role_mention = f"<@&{info['role_id']}>" if info.get("role_id") else "Aucun rôle"
        embed.add_field(
            name=f"🏆 {info['name']}",
            value=f"**{info['xp']}** XP\n*Rôle : {role_mention}*",
            inline=True
        )

    await ctx.send(embed=embed)

@bot.command()
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    user_data = data["users"].get(str(member.id))

    if not user_data:
        await ctx.send(f"❌ {member.mention} n'a pas encore gagné d'XP.")
        return

    team_info = data["teams"].get(user_data["team_key"], {})
    team_name = team_info.get("name", "Équipe inconnue")

    embed = discord.Embed(title=f"Profil de {member.display_name}", color=discord.Color.blue())
    embed.add_field(name="Équipe", value=team_name, inline=True)
    embed.add_field(name="XP Personnel", value=f"**{user_data['xp']}** XP", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)

    await ctx.send(embed=embed)

# --- METTONS TON TOKEN ICI ---
bot.run("MTU2MTEwMjg0MzQ2NzkyNzU4Mg.GG2oNb.eud6qTebw0OKm19d1S8cnBL5VfSgJSkx0i1Miw")