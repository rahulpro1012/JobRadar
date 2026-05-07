import { useState } from 'react';
import { X, Plus } from 'lucide-react';

export default function TagInput({ tags, onChange, placeholder, tagClass }) {
  const [inputValue, setInputValue] = useState('');

  const addTag = () => {
    const value = inputValue.trim();
    if (!value) return;
    if (tags.includes(value)) {
      setInputValue('');
      return;
    }
    onChange([...tags, value]);
    setInputValue('');
  };

  const removeTag = (index) => {
    onChange(tags.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTag();
    }
    // Remove last tag on backspace if input is empty
    if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
      removeTag(tags.length - 1);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {tags.map((tag, i) => (
          <span
            key={`${tag}-${i}`}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium ${tagClass || 'skill-tag'}`}
          >
            {tag}
            <button
              onClick={() => removeTag(i)}
              className="opacity-50 hover:opacity-100 transition-opacity ml-0.5"
              type="button"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || 'Type and press Enter...'}
          className="input text-sm flex-1"
        />
        <button
          onClick={addTag}
          disabled={!inputValue.trim()}
          className="btn-secondary text-xs shrink-0 disabled:opacity-30"
          type="button"
        >
          <Plus className="w-3.5 h-3.5" /> Add
        </button>
      </div>
    </div>
  );
}
