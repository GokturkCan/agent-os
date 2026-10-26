import { useEffect, useRef, useState } from 'react';
export function Modal({ open, children }: { open: boolean; children: React.ReactNode }) {
  const [y, setY] = useState(0);
  const raf = useRef(0);
  useEffect(() => {
    const tick = () => { setY((v) => v + 4); raf.current = requestAnimationFrame(tick); };
    if (open) tick();
    return () => cancelAnimationFrame(raf.current);
  }, [open]);
  return (
    <>
      <div className={`backdrop ${open ? 'open' : ''}`} />
      <div className={`modal ${open ? 'open' : ''}`} style={{ marginTop: y % 3 }}>{children}</div>
    </>
  );
}
