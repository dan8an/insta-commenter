import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api, type Activity} from './api';
import {Button} from './components/ui/button';

type PostedComment = Activity & {username: string | null; confirmed_at: number | null};
type History = {total: number; matched: number; accounts: {username: string; count: number}[]; more: boolean; items: PostedComment[]};

const pageSize = 25;

export function CommentHistory(){
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const params = new URLSearchParams({q: search, offset: String(offset)});
  selected.forEach(name => params.append('account', name));
  function changeAccounts(names: string[]) {
    setSelected(names);
    setOffset(0);
  }
  const {data, isError} = useQuery({
    queryKey: ['activity', 'posted', search, offset, selected],
    queryFn: () => api<History>(`/comments/history?${params}`),
    refetchInterval: 5000
  });
  const page = Math.floor(offset / pageSize) + 1;
  const pages = Math.ceil((data?.matched ?? 0) / pageSize);
  const visiblePages = [...new Set([1, page - 1, page, page + 1, pages])]
    .filter(number => number >= 1 && number <= pages).sort((a, b) => a - b);
  function goToPage(number: number) {
    setOffset((number - 1) * pageSize);
  }

  return <section className="activity posted-history" aria-label="Posted comments">
    <div className="activity-heading"><h2>Comments posted <span>{data?.total?.toLocaleString() ?? '…'}</span></h2>
      <a href="/api/comments/history.csv" download>Download all as CSV</a></div>
    <div className="history-controls"><label>Search posted comments <input type="search" placeholder="Account, comment, or post URL" value={search}
      onChange={event => {setSearch(event.target.value); setOffset(0)}} /></label>
    <details className="account-filter"><summary>Accounts · {selected.length || 'All'}</summary>
      <fieldset><legend>Filter by account</legend>
        <button type="button" onClick={() => changeAccounts([])}>All accounts ({data?.total?.toLocaleString() ?? '…'})</button>
        {data?.accounts?.map(({username, count}) => <label key={username}>
          <input type="checkbox" checked={selected.includes(username)} onChange={event =>
            changeAccounts(event.target.checked ? [...selected, username] : selected.filter(name => name !== username))}/>
          @{username} <span>{count.toLocaleString()}</span></label>)}
      </fieldset>
    </details></div>
    <div className="account-chips">{selected.map(name => <button key={name} aria-label={`Remove @${name} filter`}
      onClick={() => changeAccounts(selected.filter(value => value !== name))}>@{name} ×</button>)}</div>
    {(selected.length > 0 || search.trim()) && data && <p role="status">{data.matched?.toLocaleString()} matching comments · {data.total?.toLocaleString()} total</p>}
    {isError && <p role="alert">Comment history could not load.</p>}
    {data?.items?.length === 0 && <p>{search || selected.length ? 'No matching comments.' : 'No confirmed comments yet.'}</p>}
    {data?.items?.map(item => <article key={item.id} className="activity-row">
      <div className="activity-text"><strong>{item.username ? '@'+item.username : 'Account unavailable'}</strong>
        <p>{item.message}</p><a href={item.post_url} target="_blank" rel="noreferrer">Open post</a></div>
      <small>{item.confirmed_at ? 'Confirmed' : 'Submitted'} {new Date((item.confirmed_at ?? item.created_at)*1000).toLocaleString()}</small>
    </article>)}
    {pages > 0 && <nav className="history-pagination" aria-label="Comment history pages">
      <span role="status">Page {page.toLocaleString()} of {pages.toLocaleString()}</span>
      <div className="page-buttons">
        <Button variant="outline" disabled={page === 1} onClick={() => goToPage(page - 1)}>Previous</Button>
        {visiblePages.map((number, index) => <span className="page-step" key={number}>
          {index > 0 && number > visiblePages[index - 1] + 1 && <span aria-hidden="true">…</span>}
          <Button variant={number === page ? 'default' : 'outline'} aria-label={`Page ${number}`}
            aria-current={number === page ? 'page' : undefined} onClick={() => goToPage(number)}>{number}</Button>
        </span>)}
        <Button variant="outline" disabled={page >= pages} onClick={() => goToPage(page + 1)}>Next</Button>
      </div>
    </nav>}
  </section>;
}
