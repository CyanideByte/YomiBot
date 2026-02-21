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
from osrs.llm.identification_optimized import unified_identification
from osrs.llm.llm_service import LLMServiceError
from osrs.llm.agentic_loop import run_agentic_loop

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
                await processing_msg.edit(content=f"Sorry, the AI service is currently rate limited. Please try again later.")
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
                    # Try to identify players from the query using unified identification
                    result = await unified_identification(
                        user_query=user_query,
                        guild_members=guild_member_names,
                        requester_name=ctx.author.display_name
                    )

                    # Extract player information from result
                    if result["player_scope"] == "all_members":
                        await processing_msg.edit(content="I can't roast everyone at once! Pick someone specific to roast.")
                        return
                    elif result["player_scope"] == "specific_members":
                        # Use the first identified player
                        target_player = result["mentioned_players"][0] if result["mentioned_players"] else user_query
                    else:
                        # No players found, try the user query directly
                        target_player = user_query

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
                await processing_msg.edit(content=f"Sorry, the AI service is currently rate limited. Please try again later.")
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

            # Construct the API URL (updated format) SEED PARAM BROKEN
            url = f"https://pollinations.ai/p/{encoded_prompt}?enhance=true&nologo=true&model=flux"

            print(f"Requesting image from: {url}")

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

    @bot.command(name='roll', help='Rolls a 6-sided die')
    async def roll(ctx):
        result = random.randint(1, 6)
        await ctx.send(f"🎲 {ctx.author.display_name} rolled a **{result}**!", reference=ctx.message)

    @bot.command(name='agent', help='Agentic loop - iteratively gather information before responding')
    async def agent(ctx, *, user_query: str = ""):
        """
        Agentic loop command that allows the LLM to iteratively gather information
        by calling tools multiple times before generating a final response.

        Shows detailed progress updates with iteration counters and what's being fetched.
        """

        ##############################################################################################################################
        await ctx.send("Command currently disabled for testing. Please use !ask for now.", reference=ctx.message)
        return
        ##############################################################################################################################

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

        # If no query text, show error
        if not user_query:
            await ctx.send("Please provide a question for the agent. Example: !agent What's the best gear for Vorkath?")
            return

        # Combine replied message content with the user query
        combined_query = replied_message_content + user_query

        # Let the user know we're processing their request
        processing_msg = await ctx.send(
            "Initializing agentic loop - gathering information iteratively...",
            reference=ctx.message
        )

        try:
            # Get guild members
            guild_members_data = get_guild_members_data()
            guild_member_names = [member['player']['displayName'] for member in guild_members_data]

            # Run the agentic loop
            response = await run_agentic_loop(
                user_query=combined_query,
                guild_members=guild_member_names,
                requester_name=ctx.author.display_name,
                status_message=processing_msg,
                max_iterations=3
            )

            # Send the final response
            if len(response) > 1900:
                # Use the send_long_response helper from query_processing
                from osrs.llm.query_processing import send_long_response
                await send_long_response(processing_msg, response)
            else:
                await processing_msg.edit(content=response)

        except LLMServiceError as e:
            # If there was an LLM service error, inform the user
            if hasattr(e, 'retry_after') and e.retry_after:
                await processing_msg.edit(content=f"Sorry, the AI service is currently rate limited. Please try again later.")
            else:
                await processing_msg.edit(content="Sorry, the AI service is currently unavailable or overloaded. Please try again later.")
        except Exception as e:
            # If there was any other error, edit the processing message with the error
            await processing_msg.edit(content=f"Error processing your request: {str(e)}")