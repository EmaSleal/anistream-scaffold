"use client";

import { useState, useRef, useEffect, useId } from "react";
import { createPortal } from "react-dom";
import styles from "./Select.module.css";

export interface SelectOption {
  label: string;
  value: string;
}

interface SelectProps {
  options: SelectOption[];
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
  className?: string;
  "aria-label"?: string;
}

export function Select({ options, placeholder, value, onChange, className, "aria-label": ariaLabel }: SelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value);
  const displayLabel = selected?.label ?? placeholder ?? "Select…";
  const hasValue = Boolean(selected);

  // Compute dropdown position from trigger's bounding rect (portal needs absolute coords)
  function openDropdown() {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setDropdownStyle({
      position: "fixed",
      top: rect.bottom + 4,
      left: rect.left,
      minWidth: rect.width,
      zIndex: 9999,
    });
    setIsOpen(true);
  }

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (triggerRef.current && !triggerRef.current.contains(target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setIsOpen(false);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isOpen]);

  // Reposition on scroll/resize while open
  useEffect(() => {
    if (!isOpen) return;
    function reposition() {
      if (!triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      setDropdownStyle((prev) => ({ ...prev, top: rect.bottom + 4, left: rect.left, minWidth: rect.width }));
    }
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [isOpen]);

  function select(val: string) {
    onChange?.(val);
    setIsOpen(false);
  }

  const dropdown = isOpen && (
    <ul id={listId} role="listbox" className={styles.dropdown} style={dropdownStyle} aria-label={ariaLabel}>
      {placeholder && (
        <li
          role="option"
          aria-selected={!hasValue}
          className={`${styles.option} ${!hasValue ? styles.optionSelected : ""}`}
          onMouseDown={(e) => { e.preventDefault(); select(""); }}
        >
          {placeholder}
        </li>
      )}
      {options.map((opt) => {
        const isSelected = opt.value === value;
        return (
          <li
            key={opt.value}
            role="option"
            aria-selected={isSelected}
            className={`${styles.option} ${isSelected ? styles.optionSelected : ""}`}
            onMouseDown={(e) => { e.preventDefault(); select(opt.value); }}
          >
            {opt.label}
            {isSelected && (
              <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={styles.checkIcon}>
                <path d="M3 8l3.5 3.5L13 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </li>
        );
      })}
    </ul>
  );

  return (
    <div className={`${styles.wrapper} ${className ?? ""}`}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.trigger} ${isOpen ? styles.triggerOpen : ""} ${hasValue ? styles.triggerActive : ""}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => (isOpen ? setIsOpen(false) : openDropdown())}
      >
        <span className={styles.triggerLabel}>{displayLabel}</span>
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ""}`}>
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {typeof document !== "undefined" && createPortal(dropdown, document.body)}
    </div>
  );
}
