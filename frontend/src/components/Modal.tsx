import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

interface ModalProps {
  title: string;
  children: ReactNode;
  onClose: () => void;
  /** Width class — defaults to max-w-lg */
  maxWidth?: string;
}

/** Accessible modal dialog with dark backdrop and focus trap. */
export default function Modal({
  title,
  children,
  onClose,
  maxWidth = "max-w-lg",
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Focus the close button on open
  useEffect(() => {
    closeBtnRef.current?.focus();
  }, []);

  // Prevent body scroll
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      onClick={handleBackdropClick}
    >
      <div
        ref={dialogRef}
        className={[
          "relative w-full rounded-xl border border-zinc-700 bg-zinc-800 shadow-2xl",
          maxWidth,
        ].join(" ")}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-700 px-6 py-4">
          <h2
            id="modal-title"
            className="text-base font-semibold text-zinc-100"
          >
            {title}
          </h2>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-700 hover:text-zinc-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
            aria-label="Close modal"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[calc(100vh-10rem)] overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>
  );
}
