<?php
// Check if id parameter is set, otherwise use a default value
$id = isset($_GET['id']) ? htmlspecialchars($_GET['id']) : '1037423880568057867';

// Construct the JSON file path and trigger file path based on the id parameter
$json_file = "/home/ubuntu/musicbot/queues/queue_{$id}.json";
$currently_playing_file = "/home/ubuntu/musicbot/queues/currently_playing_{$id}.json";

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

header('Content-Type: application/json');
echo json_encode([
    'current_song' => $current_song,
    'next_song' => $next_song,
    'songs' => $songs
]);
?>
