<?php
// Check if id parameter is set, otherwise use a default value
$id = isset($_GET['id']) ? htmlspecialchars($_GET['id']) : '1037423880568057867';

// Construct the JSON file path and trigger file path based on the id parameter
$json_file = "/home/ubuntu/musicbot/queues/queue_{$id}.json";
$currently_playing_file = "/home/ubuntu/musicbot/queues/currently_playing_{$id}.json";
$trigger_file = "/home/ubuntu/musicbot/queues/reload_trigger_{$id}.txt";

// Read the JSON file for queue
if (file_exists($json_file)) {
    $json_data = file_get_contents($json_file);
    $songs = json_decode($json_data, true);
} else {
    $songs = [];
}

// Read the JSON file for currently playing song
if (file_exists($currently_playing_file)) {
    $current_song_data = file_get_contents($currently_playing_file);
    $current_song_info = json_decode($current_song_data, true);
    $current_song = $current_song_info['currently_playing'] ?? null;
    $next_song = $current_song_info['next_song'] ?? null;
} else {
    $current_song = null;
    $next_song = null;
}

// Extract the YouTube video ID for the thumbnail
function getYouTubeThumbnail($url) {
    parse_str(parse_url($url, PHP_URL_QUERY), $query);
    return "https://img.youtube.com/vi/" . $query['v'] . "/hqdefault.jpg";
}

// Handle the delete request
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['delete'])) {
    $delete_index = (int)$_POST['delete'];

    // Check if the index is valid
    if ($delete_index >= 0 && $delete_index < count($songs)) {
        // Remove the song from the array
        array_splice($songs, $delete_index, 1);

        // Check if the file is writable
        if (is_writable($json_file)) {
            // Save the updated array back to the JSON file
            if (file_put_contents($json_file, json_encode($songs)) === false) {
                echo "<p>Error: Could not write to JSON file.</p>";
            } else {
                // Create or modify the trigger file
                touch($trigger_file);

                // Redirect to the same page to reflect the changes
                header("Location: " . $_SERVER['PHP_SELF'] . "?id=" . urlencode($id));
                exit;
            }
        } else {
            echo "<p>Error: JSON file is not writable.</p>";
        }
    } else {
        echo "<p>Error: Invalid index for deletion.</p>";
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yomi Music Bot</title>
	<link rel="icon" href="/favicon.ico" type="image/x-icon">
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" rel="stylesheet">
    <style>
        html, body {
            height: 100%;
            margin: 0;
            padding: 0;
            background: black;
            color: #48BB78; /* Tailwind green-500 */
            font-family: sans-serif;
            overflow: auto; /* Ensure the body can scroll */
        }
        .container {
            max-height: none; /* Allow the container to grow with the content */
            overflow-y: visible; /* Disable internal scrolling */
        }
        .progress-container {
            max-width: 300px; /* Adjusted to match the title length */
        }
        .song-info {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
            text-align: center; /* Center-align text */
        }
        .controls-container {
            display: flex;
            justify-content: center;
            align-items: center;
            margin-top: 10px;
        }
        .progress-time {
            width: 50px;
            text-align: center;
        }
        .progress-wrapper {
            display: flex;
            align-items: center;
            gap: 5px; /* Adjusted to reduce space */
        }
        .progress-bar-container {
            flex: 1;
            display: flex;
            align-items: center;
        }
        .progress-bar-wrapper {
            width: 100%;
            background-color: #4A5568; /* Tailwind gray-600 */
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            background-color: #48BB78; /* Tailwind green-500 */
            transition: width 0.5s ease;
        }
    </style>
</head>
<body class="bg-black text-green-400 font-sans">
    <div class="container mx-auto p-4">
        <div class="flex justify-center mb-8">
            <img src="yomimusic.png" alt="Header Image" class="w-80 h-80 rounded-lg">
        </div>
        <h2 class="text-3xl text-center mb-8">Currently Playing</h2>
        <div class="bg-gray-800 rounded-lg shadow-lg overflow-hidden mx-auto mb-8 p-4 currently-playing-container" style="max-width: 600px;">
            <?php if ($current_song): ?>
                <div class="flex items-start">
                    <a href="<?php echo htmlspecialchars($current_song['url']); ?>" target="_blank" class="mr-4">
                        <img src="<?php echo getYouTubeThumbnail($current_song['url']); ?>" alt="Song Image" class="w-32 h-32 rounded-lg">
                    </a>
                    <div class="flex-1 song-info">
                        <div>
                            <a href="<?php echo htmlspecialchars($current_song['url']); ?>" target="_blank" class="text-green-300 underline">
                                <h3 class="text-xl"><?php echo htmlspecialchars($current_song['title']); ?></h3>
                            </a>
                            <p><?php echo htmlspecialchars($current_song['channel']); ?></p>
                        </div>
                        <div class="progress-wrapper mt-2">
                            <span id="current-time" class="progress-time">00:00</span>
                            <div class="progress-bar-container">
                                <div class="progress-bar-wrapper">
                                    <div id="progress-bar" class="progress-bar" style="width: 0%;"></div>
                                </div>
                            </div>
                            <span class="progress-time"><?php echo gmdate("i:s", $current_song['duration']); ?></span>
                        </div>
                        <div class="controls-container">
                            <button class="text-green-500 hover:text-green-700 mx-2"><i class="fas fa-backward"></i></button>
                            <button class="text-green-500 hover:text-green-700 mx-2"><i class="fas fa-pause"></i></button>
                            <button class="text-green-500 hover:text-green-700 mx-2"><i class="fas fa-forward"></i></button>
                        </div>
                    </div>
                </div>
            <?php else: ?>
                <p class="text-center">No song is currently playing.</p>
            <?php endif; ?>
        </div>

        <h2 class="text-3xl text-center mb-8">Queue</h2>
        <div class="bg-gray-800 rounded-lg shadow-lg overflow-hidden mx-auto" style="display: table;">
            <table class="table-auto mx-auto queue-container">
                <?php if ($next_song): ?>
                    <tr class="border-t border-gray-700">
                        <td class="px-4 py-2">1</td>
                        <td class="px-4 py-2 whitespace-no-wrap">
                            <a href="<?php echo htmlspecialchars($next_song['url']); ?>" target="_blank" class="text-green-300 underline">
                                <?php echo htmlspecialchars($next_song['title']); ?>
                            </a>
                        </td>
                        <td class="px-4 py-2 whitespace-no-wrap"><?php echo htmlspecialchars($next_song['channel']); ?></td>
                        <td class="px-4 py-2 whitespace-no-wrap"><?php echo gmdate("i:s", $next_song['duration']); ?></td>
                        <td class="px-4 py-2 text-center">
                            <form method="POST" action="" class="inline">
                                <input type="hidden" name="delete" value="0">
                                <button type="submit" class="text-green-500 hover:text-green-700">
                                    <i class="fas fa-times-circle"></i>
                                </button>
                            </form>
                        </td>
                    </tr>
                <?php endif; ?>
                <?php if (!empty($songs)): ?>
                    <?php foreach ($songs as $index => $song): ?>
                        <tr class="border-t border-gray-700">
                            <td class="px-4 py-2"><?php echo $index + 1 + ($next_song ? 1 : 0); ?></td>
                            <td class="px-4 py-2 whitespace-no-wrap">
                                <a href="<?php echo htmlspecialchars($song['url']); ?>" target="_blank" class="text-green-300 underline">
                                    <?php echo htmlspecialchars($song['title']); ?>
                                </a>
                            </td>
                            <td class="px-4 py-2 whitespace-no-wrap"><?php echo htmlspecialchars($song['channel']); ?></td>
                            <td class="px-4 py-2 whitespace-no-wrap"><?php echo gmdate("i:s", $song['duration']); ?></td>
                            <td class="px-4 py-2 text-center">
                                <form method="POST" action="" class="inline">
                                    <input type="hidden" name="delete" value="<?php echo $index; ?>">
                                    <button type="submit" class="text-green-500 hover:text-green-700">
                                        <i class="fas fa-times-circle"></i>
                                    </button>
                                </form>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                <?php else: ?>
                    <tr class="border-t border-gray-700">
                        <td class="px-4 py-2 text-center" colspan="5">The queue is empty.</td>
                    </tr>
                <?php endif; ?>
            </table>
        </div>
    </div>

    <script>
        let duration = <?php echo $current_song ? $current_song['duration'] : 0; ?>;
        let startTime = <?php echo $current_song ? $current_song['start_time'] : 0; ?>;
        let currentSongId = <?php echo $current_song ? json_encode($current_song['url']) : 'null'; ?>;
        let intervalId;

        function getYouTubeThumbnail(url) {
            const urlParams = new URLSearchParams(new URL(url).search);
            return "https://img.youtube.com/vi/" + urlParams.get('v') + "/hqdefault.jpg";
        }

        function fetchCurrentState() {
            fetch('get_current_state.php?id=<?php echo $id; ?>')
                .then(response => response.json())
                .then(data => {
                    if (data.current_song && data.current_song.url !== currentSongId) {
                        updateCurrentlyPlaying(data.current_song);
                        currentSongId = data.current_song.url;
                    }
                    updateQueue(data.songs, data.next_song);
                })
                .catch(error => console.error('Error fetching current state:', error));
        }

        function updateCurrentlyPlaying(song) {
            const container = document.querySelector('.currently-playing-container');
            if (!song) {
                container.innerHTML = '<p class="text-center">No song is currently playing.</p>';
                return;
            }

            duration = song.duration;
            startTime = song.start_time;

            container.innerHTML = `
                <div class="flex items-start">
                    <a href="${song.url}" target="_blank" class="mr-4">
                        <img src="${getYouTubeThumbnail(song.url)}" alt="Song Image" class="w-32 h-32 rounded-lg">
                    </a>
                    <div class="flex-1 song-info">
                        <div>
                            <a href="${song.url}" target="_blank" class="text-green-300 underline">
                                <h3 class="text-xl">${song.title}</h3>
                            </a>
                            <p>${song.channel}</p>
                        </div>
                        <div class="progress-wrapper mt-2">
                            <span id="current-time" class="progress-time">00:00</span>
                            <div class="progress-bar-container">
                                <div class="progress-bar-wrapper">
                                    <div id="progress-bar" class="progress-bar" style="width: 0%;"></div>
                                </div>
                            </div>
                            <span class="progress-time">${new Date(duration * 1000).toISOString().substr(14, 5)}</span>
                        </div>
                        <div class="controls-container">
                            <button class="text-green-500 hover:text-green-700 mx-2"><i class="fas fa-backward"></i></button>
                            <button class="text-green-500 hover:text-green-700 mx-2"><i class="fas fa-pause"></i></button>
                            <button class="text-green-500 hover:text-green-700 mx-2"><i class="fas fa-forward"></i></button>
                        </div>
                    </div>
                </div>
            `;

            clearInterval(intervalId);
            intervalId = setInterval(updateProgressBar, 1000);
        }

        function updateQueue(songs, nextSong) {
            const queueContainer = document.querySelector('.queue-container');
            let queueHTML = '';

            if (nextSong) {
                queueHTML += `
                    <tr class="border-t border-gray-700">
                        <td class="px-4 py-2">1</td>
                        <td class="px-4 py-2 whitespace-no-wrap">
                            <a href="${nextSong.url}" target="_blank" class="text-green-300 underline">
                                ${nextSong.title}
                            </a>
                        </td>
                        <td class="px-4 py-2 whitespace-no-wrap">${nextSong.channel}</td>
                        <td class="px-4 py-2 whitespace-no-wrap">${new Date(nextSong.duration * 1000).toISOString().substr(11, 8)}</td>
                        <td class="px-4 py-2 text-center">
                            <form method="POST" action="" class="inline">
                                <input type="hidden" name="delete" value="0">
                                <button type="submit" class="text-green-500 hover:text-green-700">
                                    <i class="fas fa-times-circle"></i>
                                </button>
                            </form>
                        </td>
                    </tr>
                `;
            }

            if (songs.length > 0) {
                songs.forEach((song, index) => {
                    queueHTML += `
                        <tr class="border-t border-gray-700">
                            <td class="px-4 py-2">${index + 1 + (nextSong ? 1 : 0)}</td>
                            <td class="px-4 py-2 whitespace-no-wrap">
                                <a href="${song.url}" target="_blank" class="text-green-300 underline">
                                    ${song.title}
                                </a>
                            </td>
                            <td class="px-4 py-2 whitespace-no-wrap">${song.channel}</td>
                            <td class="px-4 py-2 whitespace-no-wrap">${new Date(song.duration * 1000).toISOString().substr(11, 8)}</td>
                            <td class="px-4 py-2 text-center">
                                <form method="POST" action="" class="inline">
                                    <input type="hidden" name="delete" value="${index}">
                                    <button type="submit" class="text-green-500 hover:text-green-700">
                                        <i class="fas fa-times-circle"></i>
                                    </button>
                                </form>
                            </td>
                        </tr>
                    `;
                });
            } else {
                queueHTML += `
                    <tr class="border-t border-gray-700">
                        <td class="px-4 py-2 text-center" colspan="5">The queue is empty.</td>
                    </tr>
                `;
            }

            queueContainer.innerHTML = queueHTML;
        }

        function updateProgressBar() {
            const currentTimeInSeconds = Math.min(Math.floor(Date.now() / 1000) - startTime, duration);
            const progressBar = document.getElementById('progress-bar');
            const currentTimeElem = document.getElementById('current-time');
            const percentage = (currentTimeInSeconds / duration) * 100;

            progressBar.style.width = percentage + '%';
            currentTimeElem.textContent = new Date(currentTimeInSeconds * 1000).toISOString().substr(14, 5);
        }

        setInterval(fetchCurrentState, 5000); // Fetch updates every 5 seconds

        // Call fetchCurrentState once when the page loads
        fetchCurrentState();
        if (currentSongId) {
            intervalId = setInterval(updateProgressBar, 1000);
        }
    </script>
</body>
</html>
