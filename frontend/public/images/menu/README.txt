Place your product photos here to be shown in the menu.

Expected JPG filenames (lowercase, hyphenated):
  - espresso.jpg
  - espresso-macchiato.jpg
  - cappuccino.jpg
  - latte-macchiato.jpg
  - americano.jpg
  - orange-juice.jpg
  - water-sparkling.jpg
  - water-still.jpg
  - iced-tea.jpg
  - wine-white.jpg
  - wine-red.jpg
  - beer.jpg
  - spritz.jpg
  - negroni.jpg
  - mojito.jpg
  - espresso-martini.jpg
  - generic.jpg (optional; if missing the UI falls back to an SVG icon)

Guidelines:
  - Use square images (recommended 60x60 or 120x120), they render at 30x30.
  - Keep files small (<50KB each) to ensure a fast menu.
  - Real photos work best; object-fit: cover crops to square.

Fallbacks:
  - The app first tries the JPG here (e.g. espresso.jpg).
  - If missing, it falls back to an SVG with the same name in `public/icons/` (e.g. /icons/espresso.svg).
  - As a final fallback it uses `/icons/generic-drink.svg`.

You can also add new items by creating additional images here and the UI will
attempt to match by name automatically. For custom keys or names, see the
photo-key helper in `src/pages/MenuPage.js`.
