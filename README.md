# TRMNL Anki

TRMNL Anki is an add-on/plugin combination that allows a TRMNL to display your Anki flashcards. It supports multiple instances and mashups.

## TRMNL Anki Add-on

This is the add-on that is added to Anki. It scans the Anki notes at a recurring interval, gets the relevant field data for a single note, compresses it, and sends it to the TRMNL server via a webhook. It does not support images or (of course) audio.

[Install it here](https://ankiweb.net/shared/info/415381283)

### Config

Configuration is as follows.

#### `refresh_rate`

This is the rate in seconds that the add-on will fetch and send data to the TRMNL server. It does not effect how often the TRMNL device refreshes its screen. It has a hard-coded minimum of 300 seconds to avoid rate limiting from TRMNL's server. To help aid initial setup, you can force the add-on to refresh in the Anki menu under `Tools > Refresh TRMNL` (This can still be affected by the rate limiting).

#### `plugins`

An array of configuration for TRMNL Anki plugins.

#### Plugin Config

##### `enabled`

Set to `false` to stop the plugin from sending data.

##### `visible_fields`

An array of case-sensitive strings that are Anki note fields. If a note has one of these fields, it will be sent to the TRMNL server to be displayed. Data is sent in the order that the fields are listed. This means you should order the fields in the priority they should be displayed.

##### `webhook`

The webhook link for the TRMNL plugin. Found on the TRMNL website.

##### `search_query`

The query that will be executed to find notes. This takes the same syntax as the [Anki Browser](https://docs.ankiweb.net/searching.html). Double quotes must be escaped.

Example:
```json
"search_query": "(is:new OR is:learn OR is:review) \"note:Cantonese Basic\""
```

### Full Example
```json
{
    "plugins": [
        {
            "search_query": "(is:new OR is:learn OR is:review) \"note:Japanese Sentence Mine\"",
            "visible_fields": [
                "Word",
                "Meaning",
                "Sentence"
            ],
            "webhook": "https://usetrmnl.com/api/custom_plugins/replace-this-1"
        },
        {
            "search_query": "nid:1741914054864",
            "visible_fields": [
                "Word",
                "Meaning",
                "Sentence"
            ],
            "webhook": "https://usetrmnl.com/api/custom_plugins/replace-this-2"
        },
        {
            "search_query": "\"note:AnkiJazz - Theory\"",
            "visible_fields": [
                "Front",
                "Back"
            ],
            "webhook": "https://usetrmnl.com/api/custom_plugins/replace-this-3"
        }
    ],
    "refresh_rate": "300"
}
```

## TRMNL Anki Plugin

This is the plugin that is used by TRMNL. It retries the compressed data, decompresses it, and displays each field in the order it was received. HTML from fields are rendered as-is.
