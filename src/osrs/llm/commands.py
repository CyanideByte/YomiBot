# Discord command registration
import aiohttp
from osrs.llm.query_processing import process_unified_query, roast_player
from osrs.wiseoldman import fetch_player_details, get_guild_member_names
from osrs.llm.identification import identify_mentioned_players

def register_commands(bot):
    @bot.command(name='askyomi', aliases=['yomi', 'ask'])
    async def askyomi(ctx, *, user_query: str = ""):
        # Get the user's Discord ID for context tracking
        user_id = str(ctx.author.id)
        
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

        try:
            # Pass initial processing message to allow for status updates
            response = await process_unified_query(
                user_query or "What is this OSRS item?",
                user_id=user_id,
                image_urls=image_urls,
                requester_name=ctx.author.display_name,
                status_message=processing_msg
            )
            
            # Final response will be handled by process_unified_query
        except Exception as e:
            # If there was an error, edit the processing message with the error
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
            # Handle the case where the user wants to roast themselves
            if user_query.lower() == "me":
                target_player = ctx.author.display_name
            else:
                # Use identify_mentioned_players to find the player
                guild_members = get_guild_member_names()
                identified_players, is_all_members = await identify_mentioned_players(user_query, guild_members, ctx.author.display_name)
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
            
            # Fetch player details
            async with aiohttp.ClientSession() as session:
                player_data = await fetch_player_details(target_player, session)
            
            if not player_data:
                await processing_msg.edit(content=f"Couldn't find any stats for '{target_player}'. They're so irrelevant they don't even show up on WiseOldMan.")
                return
                
            # Generate the roast
            roast_response = await roast_player(player_data)
            if not roast_response:
                await processing_msg.edit(content=f"Their stats are so bad I'm actually speechless. I can't even roast '{target_player}' - they've roasted themselves just by existing.")
                return
                
            await processing_msg.edit(content=roast_response)
            
        except Exception as e:
            print(f"Error in roast command: {e}")
            await processing_msg.edit(content=f"Something went wrong while trying to roast this noob. They're probably not worth roasting anyway.")