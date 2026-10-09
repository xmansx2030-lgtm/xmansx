import { useEffect } from "react";

/** Route browser print shortcuts through the page's data preparation. */
export function usePrintShortcut(onPrint: () => void) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "p") {
        event.preventDefault();
        onPrint();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onPrint]);
}
