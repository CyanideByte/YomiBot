# Discord command registration
import aiohttp
import os
import random
from urllib.parse import quote
from osrs.llm.query_processing import process_unified_query, roast_player
from osrs.wiseoldman import (
    fetch_player_details, fetch_player_details_by_username,
    get_guild_members_data, get_player_cache_path
)
from osrs.llm.identification import identify_mentioned_players
from osrs.llm.llm_service import LLMServiceError

def register_commands(bot):
    @bot.command(name='askyomi', aliases=['yomi', 'ask'])
    async def askyomi(ctx, *, user_query: str = ""):
        # Get the user's Discord ID for context tracking
        user_id = str(ctx.author.id)

        # Initialize replied_message_content
        replied_message_content = ""

        # Check if the command is a reply to another message
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                referenced_message = await ctx.fetch_message(ctx.message.reference.message_id)
                if referenced_message and referenced_message.content:
                    replied_message_content = f"User replying to message: \"{referenced_message.content}\"\n\nUser message: "
            except Exception as e:
                print(f"Error fetching replied message: {e}")
        
        # Check for image attachments
        image_urls = []
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    image_urls.append(attachment.url)

        # If no query text and no images, show error
        if not user_query and not image_urls:
            await ctx.send("Please provide a question or attach an image to analyze.")
            return

        # Let the user know we're processing their request and store the message object
        # Use reference parameter to make it a reply to the user's message
        if image_urls:
            processing_msg = await ctx.send(
                "Processing your image(s) and request, this may take a moment...",
                reference=ctx.message
            )
        else:
            processing_msg = await ctx.send(
                "Processing your request, this may take a moment...",
                reference=ctx.message
            )

        # Combine replied message content with the user query
        combined_query = replied_message_content + user_query

        try:
            # Pass initial processing message to allow for status updates
            response = await process_unified_query(
                combined_query or "What is this OSRS item?", # Use combined_query
                user_id=user_id,
                image_urls=image_urls,
                requester_name=ctx.author.display_name,
                status_message=processing_msg
            )
            
            # Final response will be handled by process_unified_query
        except LLMServiceError as e:
            # If there was an LLM service error, inform the user that the service is unavailable
            if hasattr(e, 'retry_after') and e.retry_after:
                await processing_msg.edit(content=f"Sorry, the AI service is currently rate limited. Please try again in {e.retry_after} seconds.")
            else:
                await processing_msg.edit(content="Sorry, the AI service is currently unavailable or overloaded. Please try again later.")
            return
        except Exception as e:
            # If there was any other error, edit the processing message with the error
            await processing_msg.edit(content=f"Error processing your request: {str(e)}")

    @bot.command(name='roast', help='Roasts a player based on their OSRS stats.')
    async def roast(ctx, *, user_query=None):
        """Command to roast a player based on their OSRS stats."""
        if user_query is None:
            await ctx.send("Please provide a username to roast. Example: !roast zezima")
            return
            
        # Let the user know we're processing their request
        processing_msg = await ctx.send(
            "Finding player to roast...",
            reference=ctx.message
        )

        try:
            # Get guild members data first since we'll need it either way
            guild_members_data = get_guild_members_data()
            guild_member_names = [member['player']['displayName'] for member in guild_members_data]

            # Handle the case where the user wants to roast themselves
            if user_query.lower() == "me":
                target_player = ctx.author.display_name
            else:
                # Check if the query matches a guild member
                exact_match = next((member for member in guild_members_data
                                  if member['player']['displayName'].lower() == user_query.lower()), None)
                
                if exact_match:
                    # Use the exact match
                    target_player = exact_match['player']['displayName']
                    print("Exact match found, skipping identification:", target_player)
                else:
                    # Try to identify players from the query
                    identified_players, is_all_members = await identify_mentioned_players(user_query, guild_member_names, ctx.author.display_name)
                    if is_all_members:
                        await processing_msg.edit(content="I can't roast everyone at once! Pick someone specific to roast.")
                        return
                    elif not identified_players:
                        # If no players found in guild, try the user query directly
                        target_player = user_query
                    else:
                        # Use the first identified player
                        target_player = identified_players[0]

            await processing_msg.edit(content=f"Preparing a savage roast for {target_player}...")
            
            # Fetch player details, passing guild members data for efficient caching
            async with aiohttp.ClientSession() as session:
                player_data = await fetch_player_details_by_username(target_player, guild_members_data, session)
            
            if not player_data:
                await processing_msg.edit(content=f"Couldn't find any stats for '{target_player}'. They're so irrelevant they don't even show up on WiseOldMan.")
                return
                
            # Generate the roast
            roast_response = await roast_player(player_data, status_message=processing_msg)
            if not roast_response:
                await processing_msg.edit(content=f"Their stats are so bad I'm actually speechless. I can't even roast '{target_player}' - they've roasted themselves just by existing.")
                return
                
            await processing_msg.edit(content=roast_response)
            
        except LLMServiceError as e:
            # If there was an LLM service error, inform the user that the service is unavailable
            if hasattr(e, 'retry_after') and e.retry_after:
                await processing_msg.edit(content=f"Sorry, the AI service is currently rate limited. Please try again in {e.retry_after} seconds.")
            else:
                await processing_msg.edit(content="Sorry, the AI service is currently unavailable or overloaded. Please try again later.")
            return
        except Exception as e:
            print(f"Error in roast command: {e}")
            await processing_msg.edit(content=f"Something went wrong while trying to roast this noob. They're probably not worth roasting anyway.")

    @bot.command(name='image', help='Generates an image based on your prompt', aliases=['imagine'])
    async def generate_image(ctx, *, prompt: str = ""):
        if not prompt:
            await ctx.send("Please provide a prompt for the image. Example: !image a majestic dragon")
            return

        # Send initial processing message
        processing_msg = await ctx.send(
            "Generating image...",
            reference=ctx.message
        )

        try:
            # Generate random seed and encode prompt
            seed = random.randint(1, 1000000)
            encoded_prompt = quote(prompt)
            
            # Construct the API URL
            url = f"https://pollinations.ai/prompt/{encoded_prompt}?seed={seed}&nologo=true&model=flux&enhance=true"

            # Make the request to get the image
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await processing_msg.edit(content=f"Error: Failed to generate image (Status {response.status})")
                        return
                    
                    # Get the image data
                    image_data = await response.read()
                    
                    # Edit the message with the image
                    from discord import File
                    from io import BytesIO
                    
                    # Create a file-like object from the image data
                    file = File(BytesIO(image_data), filename="generated_image.jpg")
                    await processing_msg.edit(content=f"🎨 Generated image for: {prompt}", attachments=[file])

        except Exception as e:
            print(f"Error in image command: {e}")
            await processing_msg.edit(content=f"Sorry, something went wrong while generating the image: {str(e)}")