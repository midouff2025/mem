import discord
from discord.ext import commands, tasks
from flask import Flask
import threading
import os
import asyncio
import aiohttp

# --- Flask Keep-Alive ---
app = Flask(__name__)
bot_name = "Loading..."
WELCOME_CHANNEL_ID = 123456789012345678  # ضع هنا ID الشانل

@app.route("/")
def home():
    return f"Bot {bot_name} is operational"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- Discord Bot Setup ---
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Missing DISCORD_BOT_TOKEN in environment variables")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True   # ضروري عشان نرصد دخول الأعضاء
        super().__init__(command_prefix="!", intents=intents)
        self.session = None
        self.invites = {}  # نخزن الدعوات الحالية

    async def setup_hook(self):
        # aiohttp session
        self.session = aiohttp.ClientSession()
        # Flask thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print("🚀 Flask server started in background")
        # tasks
        self.update_status.start()
        self.keep_alive.start()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        global bot_name
        bot_name = self.user.name
        print(f"✅ Logged in as {self.user}")
        # حفظ الدعوات الحالية
        for guild in self.guilds:
            try:
                self.invites[guild.id] = await guild.invites()
            except discord.Forbidden:
                print(f"⚠️ Missing permission to view invites in {guild.name}")

    # --- Keep-Alive ---
    @tasks.loop(minutes=1)
    async def keep_alive(self):
        if self.session:
            try:
                url = "https://check-ban-e7pa.onrender.com"
                async with self.session.get(url) as response:
                    print(f"💡 Keep-Alive ping status: {response.status}")
            except Exception as e:
                print(f"⚠️ Keep-Alive error: {e}")

    @keep_alive.before_loop
    async def before_keep_alive(self):
        await self.wait_until_ready()

    # --- Update Status ---
    @tasks.loop(minutes=5)
    async def update_status(self):
        try:
            activity = discord.Activity(type=discord.ActivityType.watching, name=f"{len(self.guilds)} servers")
            await self.change_presence(activity=activity)
        except Exception as e:
            print(f"⚠️ Status update failed: {e}")

    @update_status.before_loop
    async def before_status_update(self):
        await self.wait_until_ready()

    # --- New Member Event ---
    async def on_member_join(self, member: discord.Member):
        inviter = "Unknown"
        try:
            # نحصل الدعوات بعد انضمام العضو
            new_invites = await member.guild.invites()
            old_invites = self.invites.get(member.guild.id, [])

            for new in new_invites:
                for old in old_invites:
                    if new.code == old.code and new.uses > old.uses:
                        inviter = f"{new.inviter} (Invite Code: {new.code})"
                        break

            # تحديث الدعوات
            self.invites[member.guild.id] = new_invites
        except discord.Forbidden:
            inviter = "Missing Permissions"

        # تجهيز Embed
        embed = discord.Embed(
            title="🎉 New Member Joined!",
            color=discord.Color.green(),
            timestamp=member.joined_at
        )
        embed.add_field(name="👤 Member", value=member.mention, inline=False)
        embed.add_field(name="🙋 Invited By", value=inviter, inline=False)
        embed.add_field(name="📊 Total Members", value=str(member.guild.member_count), inline=False)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"Welcome to {member.guild.name}!")

        # إرسال للشانل المحدد
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

# --- Run Bot ---
bot = MyBot()

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
