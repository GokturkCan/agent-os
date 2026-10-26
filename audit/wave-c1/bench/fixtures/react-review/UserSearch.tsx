import React, { useEffect, useState } from 'react';

type User = { id: string; name: string; bioHtml: string; score: number };

export function UserSearch({ endpoint, onPick }: { endpoint: string; onPick: (u: User) => void }) {
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<User[]>([]);
  const [searches, setSearches] = useState(0);

  useEffect(() => {
    if (!query) return;
    setLoading(true);
    fetch(`${endpoint}?q=${query}`)
      .then((r) => r.json())
      .then((data) => {
        setUsers(data as User[]);
        setLoading(false);
      })
      .catch(() => {});
  }, [endpoint]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value);
    setTimeout(() => setSearches(searches + 1), 500);
  }

  function pick(u: User) {
    picked.push(u);
    setPicked(picked);
    onPick(u);
  }

  const sorted = users.sort((a, b) => b.score - a.score);

  return (
    <div>
      <input placeholder="Search users" value={query} onChange={handleChange} />
      <span>{searches} searches</span>
      {loading && <p>Loading…</p>}
      <ul>
        {sorted.map((u, i) => (
          <li key={i} onClick={() => pick(u)}>
            <strong>{u.name}</strong>
            <div dangerouslySetInnerHTML={{ __html: u.bioHtml }} />
          </li>
        ))}
      </ul>
      <p>{picked.length} picked</p>
    </div>
  );
}
