Tip jar assets
==============

Drop your Zelle QR code in THIS folder as:

    zelle-qr.png

A square PNG looks best (it's shown at 176x176). Until the file exists, the
tip box shows a "coming soon" placeholder instead of breaking.

Then set your Zelle handle (email or phone) in:

    frontend/src/lib/tip.ts   ->  zelleHandle: "you@example.com"

To hide the tip box entirely, set  enabled: false  in that same file.

The tip box appears on the Plan page and the Dashboard.
