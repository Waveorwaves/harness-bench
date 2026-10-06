Build `index.html`: a real-time 3D scene of a pirate ship sailing across a moving ocean at sunset.

Aim for a stylised, cinematic look rather than photorealism, with the polish of finished artwork rather than a prototype or tech demo.

## Requirements

- **One standalone file.** Everything the page needs is inside `index.html`, including any library you use (inline it). The page is opened with no network connection, so it must not request anything else.
- **Real-time 3D with WebGL**, on a canvas that fills the browser window with no scrollbars and follows the window when it is resized.
- **A detailed ship, not a few boxes:** a shaped hull, masts, sails, rigging, cannons, railings, lanterns and deck structures, with small details visible.
- **A living ocean:** moving waves, foam, and a wake where the ship cuts through the water.
- **Sunset lighting** that shows the ship's shape and materials, with reflections on the water and a sense of depth in the atmosphere.
- **Natural motion.** The ocean, ship, sails and camera all move at a believable speed, and the ship reads as travelling through the water.
- **The viewer can orbit the camera** by dragging.
- **No text anywhere** on the page or in the scene: no titles, labels, credits or instructions.
- **It runs smoothly** and the browser console shows no errors.

## Before you finish

If you can open the page in a browser, do: look at it, check the console, and fix what you find, such as a black screen, broken geometry, a bad camera angle or missing motion.

## How it is judged

Automatic checks cover what can be measured: one file with no outside requests, no console errors, a WebGL canvas filling the window, a picture that is not blank and that moves, and no text on the page. Beyond that, people compare short clips of different attempts side by side and pick the better one.
