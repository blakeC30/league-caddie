import { RefObject, useEffect, useState } from "react";

// Conservative max height for any dropdown panel (search input + list).
// If space below the trigger is less than this, the panel opens upward.
const DROPDOWN_MAX_HEIGHT_PX = 300;

/**
 * Returns "up" when the trigger element is too close to the bottom of the
 * viewport for the dropdown panel to fit below it, and "down" otherwise.
 *
 * Usage:
 *   const direction = useDropdownDirection(containerRef, isOpen);
 *   // then on the panel div:
 *   className={direction === "up" ? "absolute bottom-full mb-1 ..." : "absolute top-full mt-1 ..."}
 */
export function useDropdownDirection(
  containerRef: RefObject<HTMLElement | null>,
  isOpen: boolean
): "down" | "up" {
  const [direction, setDirection] = useState<"down" | "up">("down");

  useEffect(() => {
    if (!isOpen || !containerRef.current) {
      setDirection("down");
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    setDirection(spaceBelow < DROPDOWN_MAX_HEIGHT_PX ? "up" : "down");
  }, [isOpen, containerRef]);

  return direction;
}
