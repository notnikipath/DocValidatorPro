import React, { useEffect, useRef, useState } from "react";

export function AppFrame({ children }) {
  const main = useRef(null);
  const [sections, setSections] = useState([]);
  useEffect(() => {
    const update = () => {
      const items = [...main.current.querySelectorAll("h2")].filter(h => h.textContent.trim()).slice(0, 4).map((heading, index) => {
        if (!heading.id) heading.id = `workspace-section-${index}`;
        return { id: heading.id, label: heading.textContent.trim() };
      });
      setSections(previous => JSON.stringify(previous) === JSON.stringify(items) ? previous : items);
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(main.current, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);
  return <div className="product-shell">
    <a className="product-skip" href="#workspace">Skip to content</a>
    <header className="product-header"><div className="product-header-inner">
      <a className="product-brand" href="#workspace" aria-label="DocValidator Pro — overview">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M14 17.5h7m-3.5-3.5v7"/></svg>
        <span><strong>DocValidator Pro</strong><small>Document quality</small></span>
      </a>
      {sections.length > 0 && <nav className="product-nav" aria-label="Workspace sections">
        {sections.map(section => <a key={section.id} href={`#${section.id}`}>{section.label}</a>)}
      </nav>}
    </div></header>
    <main id="workspace" ref={main} className="product-main" tabIndex={-1}>{children}</main>
  </div>;
}
