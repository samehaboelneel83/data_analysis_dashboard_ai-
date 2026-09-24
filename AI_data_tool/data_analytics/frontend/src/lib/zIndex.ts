// Shared z-index scale — keeps every overlay's stacking order intentional
// instead of each feature picking its own magic number.
export const Z_DROPDOWN = 50    // inline menus (e.g. "add dataset" dropdown)
export const Z_DRAG     = 100   // a widget actively being dragged/resized on the canvas
export const Z_OVERLAY  = 1000  // floating previews and modal backdrops
export const Z_MODAL_TOP = 9999 // modals that must sit above other overlays (e.g. nested builders)
