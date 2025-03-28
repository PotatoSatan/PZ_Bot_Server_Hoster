#Remind me to create .env 
#restart_times.json

import discord
from discord import app_commands
from discord.ext import tasks
import asyncio
from mcrcon import MCRcon
import os
import json
from dotenv import load_dotenv
from datetime import datetime, time
import a2s  
import socket
import traceback

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
RCON_HOST = os.getenv('RCON_HOST', 'localhost')
RCON_PORT = int(os.getenv('RCON_PORT', '27015'))
RCON_PASSWORD = os.getenv('RCON_PASSWORD')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
ROLE_ID = int(os.getenv('ROLE_ID', '0'))
QUERY_PORT = int(os.getenv('QUERY_PORT', '27016'))  
SERVER_STARTUP_TIMEOUT = 300

STORAGE_FILE = 'restart_times.json'

intents = discord.Intents.default()

class RestartTime:
    def __init__(self, hour: int, minute: int, enabled: bool = True):
        self.hour = hour
        self.minute = minute
        self.enabled = enabled

    def to_dict(self):
        return {'hour': self.hour, 'minute': self.minute, 'enabled': self.enabled}

    @classmethod
    def from_dict(cls, data):
        return cls(data['hour'], data['minute'], data['enabled'])

    def get_time(self):
        return time(self.hour, self.minute)

class RestartBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.restart_times = []
        self.load_restart_times()

    def load_restart_times(self):
        try:
            with open(STORAGE_FILE, 'r') as f:
                data = json.load(f)
                self.restart_times = [RestartTime.from_dict(t) for t in data]
        except FileNotFoundError:
            self.restart_times = [RestartTime(4, 0), RestartTime(12, 0), RestartTime(20, 0)]
            self.save_restart_times()

    def save_restart_times(self):
        with open(STORAGE_FILE, 'w') as f:
            json.dump([t.to_dict() for t in self.restart_times], f)

    @tasks.loop(minutes=1)
    async def check_restart_time(self):
        now = datetime.now().time()
        for restart_time in self.restart_times:
            if restart_time.enabled and now.hour == restart_time.hour and now.minute == restart_time.minute:
                await send_restart_sequence()
                return

    @tasks.loop(minutes=5)
    async def update_status(self):
        try:
            player_count = await get_player_count()
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{player_count} Survivors"
            )
            await self.change_presence(activity=activity, status=discord.Status.online)
            print(f"Updated status: Watching {player_count} Survivors") 
        except Exception as e:
            print(f"Error updating status: {e}")

#Need to fixa
"""async def wait_for_server_restart():
    start_time = datetime.now()
    attempt = 0
    channel = client.get_channel(CHANNEL_ID)

    print(f"Starting server restart monitoring on {RCON_HOST}:{QUERY_PORT}")
    
    while (datetime.now() - start_time).total_seconds() < SERVER_STARTUP_TIMEOUT:
        attempt += 1
        try:
            print(f"Checking server status (Attempt {attempt})...")
            if await is_server_online():
                print("Server is back online!")
                return True
                
            print(f"Server not responding (Attempt {attempt})")
            if channel:
                if attempt % 6 == 0:  # Send message every ~60 seconds
                    await channel.send(f"Still waiting for server to come back online... ({int((datetime.now() - start_time).total_seconds())}s)")
                    
        except Exception as e:
            print(f"Error checking server status (Attempt {attempt}): {str(e)}")
            
        await asyncio.sleep(10)  # Check every 10 seconds
        
    print(f"Server restart monitoring timed out after {SERVER_STARTUP_TIMEOUT} seconds")
    return False"""

#Need to fix
"""async def is_server_online():
    try:
        address = (RCON_HOST, QUERY_PORT)
        # Set a shorter timeout for the query
        timeout = 5.0  # 5 seconds timeout
        
        # Create a future for the query with timeout
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, lambda: a2s.info(address, timeout=timeout))
        
        # Wait for the query with timeout
        info = await asyncio.wait_for(future, timeout=timeout)
        return info is not None
        
    except asyncio.TimeoutError:
        print(f"Timed out for {RCON_HOST}:{QUERY_PORT}")
        return False
    except ConnectionRefusedError:
        print(f"Connection refused to {RCON_HOST}:{QUERY_PORT}")
        return False
    except Exception as e:
        print(f"Error querying server status: {str(e)}")
        return False"""

async def get_player_count():
    try:
        address = (RCON_HOST, QUERY_PORT)
        players = await asyncio.get_event_loop().run_in_executor(None, lambda: a2s.players(address))
        return len(players)
    except (socket.timeout, ConnectionRefusedError) as e:
        print(f"Server query error: {e}")
        return 0
    except Exception as e:
        print(f"Unexpected error querying server: {e}")
        try:
            address = (RCON_HOST, QUERY_PORT)
            query_info = await asyncio.get_event_loop().run_in_executor(None, lambda: a2s.rules(address))
            if hasattr(query_info, 'player_count'):
                return query_info.player_count
            return 0
        except Exception as backup_e:
            print(f"Backup query failed: {backup_e}")
            return 0

async def send_restart_sequence():
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        role_mention = f"<@&{ROLE_ID}>" if ROLE_ID != 0 else ""
        await channel.send(f"{role_mention} The server will reboot soon. Make sure to get somewhere safe, stop driving, and not move items around in your inventory.")

    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, int(RCON_PORT)) as mcr:
            for minutes in range(5, 0, -1):
                try:
                    mcr.command(f'servermsg "Server will restart in {minutes} minute{"s" if minutes > 1 else ""}"')
                    if minutes > 1:
                        await asyncio.sleep(60)
                    else:
                        await asyncio.sleep(50)
                        mcr.command('save')
                except Exception as cmd_error:
                    print(f"RCON command error: {cmd_error}")
                    await channel.send(f"Error : {cmd_error}")

        try:
            mcr.command('save')
        except Exception:
            pass

        #Need to fix
        server_back = await wait_for_server_restart()
        
        if server_back:
            if channel:
                await channel.send(f"🟢 Server is back online.")
            print("Server restart completed successfully.")
        else:
            if channel:
                await channel.send(f"Restart X.")
            print("Server restart failed to complete.")

    except Exception as e:
        print(f"Restart sequence error: {e}")
        print(traceback.format_exc())
        if channel:
            await channel.send(f"{str(e)}\n{traceback.format_exc()}")


client = RestartBot()

@client.event
async def on_ready():
    await client.tree.sync()
    print(f'{client.user} connected to Discord.')
    if not client.check_restart_time.is_running():
        client.check_restart_time.start()
    if not client.update_status.is_running():
        client.update_status.start()
    await client.update_status()

@client.tree.command(name="restart", description="Manually trigger a server restart sequence")
@app_commands.checks.has_permissions(administrator=True)
async def restart(interaction: discord.Interaction):
    await interaction.response.send_message("Starting restart warning sequence...")
    await send_restart_sequence()

@client.tree.command(name="add_restart", description="Add a new restart time (24-hour format)")
@app_commands.checks.has_permissions(administrator=True)
async def add_restart(interaction: discord.Interaction, hour: int, minute: int = 0):
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await interaction.response.send_message("Invalid time! Hour must be 0-23 and minute must be 0-59.")
        return
    new_restart = RestartTime(hour, minute)
    client.restart_times.append(new_restart)
    client.save_restart_times()
    await interaction.response.send_message(f"Added new restart time: {hour:02d}:{minute:02d}")

@client.tree.command(name="remove_restart", description="Remove a restart time by its number (use /list_restarts to see numbers)")
@app_commands.checks.has_permissions(administrator=True)
async def remove_restart(interaction: discord.Interaction, number: int):
    sorted_times = sorted(client.restart_times, key=lambda x: (x.hour, x.minute))
    if not (1 <= number <= len(sorted_times)):
        await interaction.response.send_message(f"Invalid restart time number! Use a number between 1 and {len(sorted_times)}.")
        return
    
    removed_time = sorted_times[number - 1]
    client.restart_times.remove(removed_time)
    client.save_restart_times()
    await interaction.response.send_message(f"Removed restart time #{number}: {removed_time.hour:02d}:{removed_time.minute:02d}")

@client.tree.command(name="announce", description="Send a custom announcement message to a specific channel")
@app_commands.checks.has_permissions(administrator=True)
async def announce(
    interaction: discord.Interaction, 
    channel: discord.TextChannel, 
    message: str, 
    mention_role: bool = True
):
    if mention_role and ROLE_ID != 0:
        message = message.replace("\\n", "\n")
        message = f"<@&{ROLE_ID}> {message}" 
    
    try:
        await channel.send(message)
        
        await interaction.response.send_message(
            f"Message sent to {channel.mention}", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Failed to send message: {str(e)}", 
            ephemeral=True
        )

@client.tree.command(name="embed_announce", description="Send an announcement as an embed")
@app_commands.checks.has_permissions(administrator=True)
async def embed_announce(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    description: str,
    mention_role : bool = True,
    color: str = "blurple"
):
    color_map = {
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "blue": discord.Color.blue(),
        "blurple": discord.Color.blurple(),
        "yellow": discord.Color.yellow(),
        "orange": discord.Color.orange()
    }

    embed = discord.Embed(
        title=title,
        description = description.replace("\\n", "\n"),
        color=color_map.get(color.lower(), discord.Color.blurple())
    )

    content = f"<@&{ROLE_ID}>" if ROLE_ID != 0 else None

    try:
        await channel.send(content=content, embed=embed)

        await interaction.response.send_message(
            f"Embed announcement sent to {channel.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Failed to send embed announcement: {str(e)}",
            ephemeral=True
        )

@client.tree.command(name="list_restarts", description="List all scheduled restart times")
async def list_restarts(interaction: discord.Interaction):
    if not client.restart_times:
        await interaction.response.send_message("No restart times scheduled.")
        return
    restart_list = "\n".join([f"#{i+1}: {t.hour:02d}:{t.minute:02d} {'🟢 Enabled' if t.enabled else '🔴 Disabled'}" 
                             for i, t in enumerate(sorted(client.restart_times, key=lambda x: (x.hour, x.minute)))])
    await interaction.response.send_message(f"Scheduled restart times:\n{restart_list}")

def main():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()