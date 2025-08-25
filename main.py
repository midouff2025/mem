import discord
from discord.ext import commands, tasks
from flask import Flask
import threading
import os
import asyncio
import aiohttp
import json

# --- Flask Keep-Alive ---
app = Flask(__name__)
bot_name = "Loading..."
WELCOME_CHANNEL_ID = 1403045441641250907  # ضع هنا ID القناة
DATA_FILE = "invites.json"
START_POINTS = 5  # الدعوات تبدأ من 5

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
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.session = None
        self.invites = {}

        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                self.invite_counts = json.load(f)
        else:
            self.invite_counts = {}

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print("🚀 Flask server started in background")
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
                url = "https://mem-l84g.onrender.com"
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
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers"
            )
            await self.change_presence(activity=activity)
        except Exception as e:
            print(f"⚠️ Status update failed: {e}")

    @update_status.before_loop
    async def before_status_update(self):
        await self.wait_until_ready()

    # --- New Member Event ---
    async def on_member_join(self, member: discord.Member):
        inviter = None
        try:
            new_invites = await member.guild.invites()
            old_invites = self.invites.get(member.guild.id, [])
            for new in new_invites:
                match = next((old for old in old_invites if old.code == new.code), None)
                if match and new.uses > match.uses:
                    inviter = new.inviter
                    break
            self.invites[member.guild.id] = new_invites
        except discord.Forbidden:
            inviter = None

        embed = discord.Embed(
            title="🎉 New Member Joined!",
            color=discord.Color.green(),
            timestamp=member.joined_at
        )
        embed.add_field(name="👤 Member", value=member.mention, inline=False)

        if inviter:
            uid = str(inviter.id)
            if uid not in self.invite_counts:
                self.invite_counts[uid] = START_POINTS
            self.invite_counts[uid] += 1
            with open(DATA_FILE, "w") as f:
                json.dump(self.invite_counts, f)
            total_invites = self.invite_counts[uid]
            embed.add_field(name="🙋 Invited By", value=inviter.mention, inline=False)
            embed.add_field(name="🏆 Total Invites by User", value=str(total_invites), inline=False)
        else:
            embed.add_field(name="🙋 Invited By", value="Unknown", inline=False)

        embed.add_field(name="📊 Total Members", value=str(member.guild.member_count), inline=False)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"Welcome to {member.guild.name}!")

        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

    # --- Command: !inv ---
    @commands.command()
    async def inv(self, ctx):
        uid = str(ctx.author.id)
        invites = self.invite_counts.get(uid, START_POINTS)
        embed = discord.Embed(
            title="📊 Your Invites",
            description=f"👤 {ctx.author.mention}, you have **{invites}** invites.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    # --- Block Other Messages ---
    async def on_message(self, message):
        if message.author.bot:
            return

        # ✅ عالج الأوامر أولاً
        await self.process_commands(message)

        # ⛔ بعدين امنع أي رسالة مش !inv في القناة المحددة
        if message.channel.id == WELCOME_CHANNEL_ID:
            if not message.content.startswith("!inv"):
                await message.delete()
                embed = discord.Embed(
                    title="⚠️ ممنوع إرسال رسائل هنا",
                    description="✅ فقط استخدم الأمر `!inv` لمعرفة عدد دعواتك.",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed, delete_after=5)

# --- Run Bot ---
bot = MyBot()

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
