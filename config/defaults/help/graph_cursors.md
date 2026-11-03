# Graph Cursors

The graph has two vertical cursors, **A** and **B**, for reading values off the plot.

## Placing cursors

- **Click the plot** to put cursor A there. **Shift+click** puts cursor B there.
- The **Cursor A** and **Cursor B** buttons show or hide each cursor. Showing one that hasn't been placed yet drops it in the middle of the visible range.
- **Drag a cursor** to move it. Panning and zooming the plot don't move the cursors.

## Reading values

- The times of the cursors, and the gap between them (**Δt**), appear next to the cursor buttons.
- In the **Plotted signals** table, **At cursor A** and **At cursor B** show each signal's value at that moment, and **Δ (B − A)** shows how much it changed between the two cursors.
- A dot on each trace marks where the cursor crosses it.
- CAN signals only update when a frame arrives, so a value at a cursor is the **most recent frame at or before that time**. Before a signal's first frame it shows a dash.
- State signals (on/off, gear and similar) show the state name. Their Δ shows whether the state changed.

## Snapping to a peak

The row above the table reads as a sentence: **Snap** *cursor* **to the** *Max or Min* **of** *signal* **in** *range*. Pick each part, then press **Snap**.

- **Selecting a row** in the Plotted signals table picks that signal for snapping.
- **Whole log** searches every frame. **Visible window** searches only the part of the log that's zoomed into view.

## Using the cursors elsewhere

- **Data analysis** can show statistics for just the stretch between cursors A and B: set **over** to **Between cursors A and B**.
- **Table view** has **Go to cursor A** and **Go to cursor B** to jump to the matching row.
