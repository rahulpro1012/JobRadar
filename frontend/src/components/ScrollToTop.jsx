import { useState, useEffect } from 'react';
import { ArrowUp } from 'lucide-react';

export default function ScrollToTop() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      setVisible(window.scrollY > 400);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollUp = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (!visible) return null;

  return (
    <button
      onClick={scrollUp}
      className="fixed bottom-6 left-6 z-40 w-10 h-10 rounded-full
                 bg-brand-600 text-white shadow-lg
                 hover:bg-brand-500 active:bg-brand-700
                 transition-all duration-200 hover:scale-110
                 flex items-center justify-center
                 animate-fade-in"
      title="Scroll to top"
    >
      <ArrowUp className="w-5 h-5" />
    </button>
  );
}
