# Discord command registration
from osrs.llm.query_processing import process_unified_query, roast_player
from osrs.llm.identification import identify_mentioned_players
from wiseoldman.tracker import get_guild_members, fetch_player_details

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
            # Get guild members to check if any are mentioned in the query
            guild_members = get_guild_members()
            
            # Use Gemini to identify mentioned players in the query
            mentioned_members = await identify_mentioned_players(
                user_query,
                guild_members,
                ctx.author.display_name  # Pass the requester's name
            )
            
            # Use the unified query processor
            response = await process_unified_query(
                user_query or "What is this OSRS item?",
                user_id=user_id,
                image_urls=image_urls,
                mentioned_players=mentioned_members,
                requester_name=ctx.author.display_name
            )
            
            await processing_msg.edit(content=response)
        except Exception as e:
            # If there was an error, edit the processing message with the error
            await processing_msg.edit(content=f"Error processing your request: {str(e)}")
            
    @bot.command(name='roast', help='Roasts a player based on their OSRS stats.')
    async def roast(ctx, *, username=None):
        """Command to roast a player based on their OSRS stats."""
        if username is None:
            await ctx.send("Please provide a username to roast. Example: !roast zezima")
            return

        # Handle the case where the user wants to roast themselves
        if username.lower() == "me":
            username = ctx.author.display_name
        
        # Let the user know we're processing their request
        processing_msg = await ctx.send(
            f"Preparing a roast for {username}, this may take a moment...",
            reference=ctx.message
        )
        
        try:
            # Fetch player details
            player_data = fetch_player_details(username)
            
            if player_data:
                # Generate the roast
                roast_response = await roast_player(player_data)
                await processing_msg.edit(content=roast_response)
            else:
                await processing_msg.edit(content=f"Could not find player '{username}' or an error occurred.")
        except TypeError:
            await processing_msg.edit(content=f"Error: Player data for '{username}' is not available.")
        except Exception as e:
            await processing_msg.edit(content=f"An unexpected error occurred: {str(e)}")