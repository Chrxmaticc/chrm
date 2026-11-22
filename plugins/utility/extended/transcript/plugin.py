import discord
from discord.ext import commands
import io
import datetime
import html
import re

class TranscriptMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    @commands.command()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def transcript(self, ctx, limit: int = 100):
        """exports the chat to a beautiful html file. usage: .transcript 50"""
        
        # Limit to 500 to prevent Render from running out of RAM
        if limit > 500:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} max limit is 500 messages.")
        
        loading = await ctx.send(f"{self.bot.config.get_emoji('loading')} generating transcript for {limit} messages...")

        messages = []
        try:
            async for msg in ctx.channel.history(limit=limit):
                messages.append(msg)
        except Exception as e:
            return await loading.edit(content=f"{self.bot.config.get_emoji('error')} failed to fetch history: {e}")

        if not messages:
            return await loading.edit(content=f"{self.bot.config.get_emoji('error')} no messages found.")

        # Discord returns messages newest -> oldest, so we reverse it to read like a normal chat
        messages.reverse()

        # Start building the HTML with a sleek dark mode theme
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>chrm transcript</title>
            <style>
                body {
                    background-color: #313338;
                    color: #dbdee1;
                    font-family: 'gg sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                }
                .header {
                    border-bottom: 1px solid #1e1f22;
                    padding-bottom: 20px;
                    margin-bottom: 20px;
                }
                .header h1 { margin: 0; color: #f2f3f5; font-size: 24px; }
                .header p { margin: 5px 0 0 0; color: #949ba4; font-size: 14px; }
                .chat-container {
                    display: flex;
                    flex-direction: column;
                    gap: 15px;
                }
                .message {
                    display: flex;
                    gap: 15px;
                    padding: 5px 0;
                }
                .avatar {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    object-fit: cover;
                }
                .content {
                    flex: 1;
                    min-width: 0;
                }
                .meta {
                    display: flex;
                    align-items: baseline;
                    gap: 8px;
                    margin-bottom: 4px;
                }
                .username { font-weight: 600; color: #f2f3f5; font-size: 16px; }
                .timestamp { font-size: 12px; color: #949ba4; }
                .text { font-size: 16px; line-height: 1.375; white-space: pre-wrap; word-wrap: break-word; }
                .attachment {
                    margin-top: 8px;
                    max-width: 400px;
                    border-radius: 8px;
                    display: block;
                }
                .file-link {
                    display: inline-block;
                    background-color: #2b2d31;
                    border: 1px solid #1e1f22;
                    padding: 10px;
                    border-radius: 8px;
                    color: #00a8fc;
                    text-decoration: none;
                    margin-top: 8px;
                }
                .embed {
                    border-left: 4px solid #5865F2;
                    background-color: #2b2d31;
                    padding: 12px;
                    border-radius: 4px;
                    margin-top: 8px;
                    max-width: 500px;
                }
                .embed-title { font-weight: 600; color: #f2f3f5; margin-bottom: 4px; }
                .embed-desc { font-size: 14px; color: #dbdee1; margin-bottom: 8px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Chat Transcript</h1>
                <p>Exported by chrm • {count} messages</p>
            </div>
            <div class="chat-container">
        """

        html_content = html_content.replace("{count}", str(len(messages)))

        for msg in messages:
            # Escape HTML to prevent breaking the file
            content = html.escape(msg.content) if msg.content else ""
            
            # Format timestamps
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            
            # Get Avatar (fallback to default if none)
            avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
            
            # Build message block
            html_content += f"""
                <div class="message">
                    <img src="{avatar_url}" class="avatar" alt="avatar">
                    <div class="content">
                        <div class="meta">
                            <span class="username">{html.escape(msg.author.name)}</span>
                            <span class="timestamp">{ts}</span>
                        </div>
            """
            
            if content:
                html_content += f'<div class="text">{content}</div>'
            
            # Handle Attachments
            if msg.attachments:
                for att in msg.attachments:
                    # Check if it's an image
                    if att.content_type and "image" in att.content_type:
                        html_content += f'<img src="{att.url}" class="attachment" alt="image">'
                    else:
                        html_content += f'<a href="{att.url}" class="file-link" target="_blank">📎 {att.filename}</a>'
            
            # Handle Embeds
            if msg.embeds:
                for embed in msg.embeds:
                    html_content += '<div class="embed">'
                    if embed.title:
                        html_content += f'<div class="embed-title">{html.escape(embed.title)}</div>'
                    if embed.description:
                        html_content += f'<div class="embed-desc">{html.escape(embed.description)}</div>'
                    html_content += '</div>'

            html_content += """
                    </div>
                </div>
            """

        html_content += """
            </div>
        </body>
        </html>
        """

        # Convert to a file
        file_bytes = io.BytesIO(html_content.encode('utf-8'))
        
        # Name the file based on the channel (DM, GC, or Server)
        if hasattr(ctx.channel, 'name') and ctx.channel.name:
            filename = f"transcript_{ctx.channel.name}_{len(messages)}.html"
        elif hasattr(ctx.channel, 'recipients'):
            filename = f"transcript_gc_{len(messages)}.html"
        else:
            filename = f"transcript_dm_{len(messages)}.html"

        file = discord.File(file_bytes, filename=filename)
        
        await loading.delete()
        await ctx.send(f"{self.bot.config.get_emoji('success')} transcript generated.", file=file)
