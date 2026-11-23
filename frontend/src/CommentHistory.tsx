import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api, type Activity} from './api';
import {Button} from './components/ui/button';

type PostedComment = Activity & {username: string | null; confirmed_at: number | null};
type History = {total: number; more: boolean; items: PostedComment[]};

export function CommentHistory(){
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const {data, isError} = useQuery({
    queryKey: ['activity', 'posted', search, offset],
    queryFn: () => api<History>(`/comments/history?q=${encodeURIComponent(search)}&offset=${offset}`),
    refetchInterval: 5000
  });
  return <section className="activity" aria-label="Posted comments">
    <div className="activity-heading"><h2>Comments posted <span>{data?.total?.toLocaleString() ?? '…'}</span></h2>
      <a href="/api/comments/history.csv" download>Download all as CSV</a></div>
    <label>Search posted comments <input type="search" placeholder="Account, comment, or post URL" value={search}
      onChange={event => {setSearch(event.target.value); setOffset(0)}} /></label>
    {isError && <p role="alert">Comment history could not load.</p>}
    {data?.items?.length === 0 && <p>{search ? 'No matching comments.' : 'No confirmed comments yet.'}</p>}
    {data?.items?.map(item => <article key={item.id} className="activity-row">
      <div className="activity-text"><strong>{item.username ? '@'+item.username : 'Account unavailable'}</strong>
        <p>{item.message}</p><a href={item.post_url} target="_blank" rel="noreferrer">Open post</a></div>
      <small>{item.confirmed_at ? 'Confirmed' : 'Submitted'} {new Date((item.confirmed_at ?? item.created_at)*1000).toLocaleString()}</small>
    </article>)}
    <div className="result-actions">
      {offset > 0 && <Button variant="outline" onClick={() => setOffset(offset-25)}>Previous</Button>}
      {data?.more && <Button variant="outline" onClick={() => setOffset(offset+25)}>Next</Button>}
    </div>
  </section>;
}
