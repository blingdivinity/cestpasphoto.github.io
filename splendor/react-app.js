const { useEffect, useMemo, useState } = React;
const html = htm.bind(React.createElement);

const GEM_NAMES = ['Diamond', 'Sapphire', 'Emerald', 'Ruby', 'Onyx', 'Gold'];
const TIER_NAMES = ['I', 'II', 'III'];

function useGameStore() {
  const [store, setStore] = useState(null);
  const [, render] = useState(0);

  useEffect(() => {
    let started = false;
    let effectRunner = null;
    const connect = () => {
      if (effectRunner || !window.Alpine || !Alpine.store('game')) return;
      const game = Alpine.store('game');
      setStore(game);
      effectRunner = Alpine.effect(() => {
        JSON.stringify({
          isLoading: game.isLoading,
          isThinking: game.isThinking,
          loadingMessage: game.loadingMessage,
          players: game.arePlayersHuman,
          currentPlayer: game.currentPlayer,
          gameEnded: game.gameEnded,
          winners: game.winners,
          canUndo: game.canUndo,
          difficulty: game.numMCTSSims,
          view: game.view,
          extra: game.extra
        });
        render(n => n + 1);
      });
      if (!started) {
        started = true;
        game.start();
      }
    };
    connect();
    document.addEventListener('alpine:initialized', connect);
    return () => {
      if (effectRunner) Alpine.release(effectRunner);
      document.removeEventListener('alpine:initialized', connect);
    };
  }, []);
  return store;
}

const safe = value => value || [];
const selected = (extra, type, predicate = () => true) => extra?.sel_type === type && predicate(extra.sel_items || []);
const lastAction = (extra, type, predicate = () => true) => extra?.last_action?.[0] === type && predicate(extra.last_action?.[1]);

function Icon({ name, size = 20 }) {
  const icons = {
    crown: html`<path d="M3 7l4 4 5-7 5 7 4-4-2 11H5L3 7zM5 21h14"/>`,
    spark: html`<path d="M12 2l1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5L12 2z"/>`,
    undo: html`<path d="M9 7H4v-5M4 7c2.2-2.8 5.4-4 8.6-3 4.4 1.3 6.9 5.9 5.6 10.3-1.3 4.4-5.9 6.9-10.3 5.6-2.5-.7-4.4-2.5-5.4-4.7"/>`,
    reset: html`<path d="M20 6v5h-5M20 11a8 8 0 10-.8 5"/>`,
    settings: html`<path d="M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM19.4 15a1.7 1.7 0 00.3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.6v.2h-4V21a1.7 1.7 0 00-1-1.6 1.7 1.7 0 00-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 00.3-1.9A1.7 1.7 0 003 14H2.8v-4H3a1.7 1.7 0 001.6-1 1.7 1.7 0 00-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 001.9.3A1.7 1.7 0 0010 3v-.2h4V3a1.7 1.7 0 001 1.6 1.7 1.7 0 001.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 00-.3 1.9 1.7 1.7 0 001.6 1h.2v4H21a1.7 1.7 0 00-1.6 1z"/>`,
    user: html`<path d="M20 21a8 8 0 00-16 0M12 13a5 5 0 100-10 5 5 0 000 10z"/>`,
    bot: html`<path d="M12 2v3M8 2h8M5 8h14v11H5zM2 11h3M19 11h3M9 13h.01M15 13h.01M9 17h6"/>`
  };
  return html`<svg className="icon" width=${size} height=${size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">${icons[name]}</svg>`;
}

function Gem({ index, count, compact = false, active = '', recent = false, onClick }) {
  return html`<button className=${`gem gem-${index} ${compact ? 'gem-compact' : ''} ${active ? `is-${active}` : ''} ${recent ? 'is-recent' : ''}`} onClick=${onClick} disabled=${!onClick} aria-label=${`${count} ${GEM_NAMES[index]} gems`}>
    <span className="gem-shine"></span><span className="gem-count">${count}</span><span className="gem-name">${GEM_NAMES[index]}</span>
  </button>`;
}

function Card({ card, tier, index, extra, compact = false, onClick }) {
  if (!card || card[0] < 0) return html`<div className=${`development-card card-empty ${compact ? 'compact' : ''}`}></div>`;
  const [color, points, costs] = card;
  const isMarket = tier >= 0;
  const isBuy = selected(extra, 'card', items => items[0]?.[0] === tier && items[0]?.[1] === index);
  const isReserve = selected(extra, 'rsv', items => items[0]?.[0] === tier && items[0]?.[1] === index);
  const recent = isMarket
    ? (lastAction(extra, 'card', value => value === tier * 4 + index) || lastAction(extra, 'rsv', value => value === tier * 4 + index))
    : lastAction(extra, 'buyrsv', value => value === index);
  return html`<button className=${`development-card color-${color} ${compact ? 'compact' : ''} ${isBuy ? 'is-buy' : ''} ${isReserve ? 'is-reserve' : ''} ${recent ? 'is-recent' : ''}`} onClick=${onClick} disabled=${!onClick} aria-label=${`${GEM_NAMES[color]} card worth ${points} points`}>
    <span className="card-glow"></span>
    <span className="card-top"><strong>${points || ''}</strong><span className=${`bonus bonus-${color}`}></span></span>
    <span className="card-art"><span></span></span>
    <span className="costs">${safe(costs).map(([idx, amount]) => html`<span key=${idx} className=${`cost cost-${idx}`}>${amount}</span>`)}</span>
    ${isReserve && html`<span className="selection-label">Reserve</span>`}
  </button>`;
}

function Noble({ noble, index }) {
  return html`<div className="noble" style=${{ '--delay': `${index * 70}ms` }}>
    <span className="noble-portrait"><${Icon} name="crown" size=${17}/></span>
    <span className="noble-points">3</span>
    <span className="noble-costs">${safe(noble).map(([idx, amount]) => html`<span key=${idx} className=${`mini-cost cost-${idx}`}>${amount}</span>`)}</span>
  </div>`;
}

function Deck({ tier, count, active, recent, onClick }) {
  return html`<button className=${`deck tier-${tier} ${active ? 'is-active' : ''} ${recent ? 'is-recent' : ''}`} onClick=${onClick}>
    <span className="deck-pattern"></span><span className="tier-mark">${TIER_NAMES[tier]}</span><span className="deck-count">${count}<small>cards</small></span>
  </button>`;
}

function PlayerPanel({ player, index, game }) {
  const human = game.arePlayersHuman?.[index];
  const current = game.currentPlayer === index;
  return html`<article className=${`player-panel ${current ? 'is-current' : ''}`}>
    <header className="player-header">
      <div className="player-avatar"><${Icon} name=${human ? 'user' : 'bot'} size=${20}/><span className="presence"></span></div>
      <div><p>${index === 0 ? 'You' : human ? `Player ${index + 1}` : `AI Player ${index + 1}`}</p><span>${current ? 'Taking a turn' : 'Waiting'}</span></div>
      <div className="score"><strong>${player.points}</strong><span>prestige</span></div>
    </header>
    <div className="player-assets">
      <div className="asset-row gems-owned">${safe(player.gems).map((count, idx) => html`<${Gem} key=${idx} index=${idx} count=${count} compact active=${selected(game.extra, 'gemback', items => items.includes(idx)) ? (game.extra.sel_items[0] === game.extra.sel_items[1] ? 'double' : 'active') : ''} recent=${lastAction(game.extra, 'gemback', items => items?.includes(idx)) && index === game.extra?.previous_player} onClick=${current && index === 0 && idx < 5 && count > 0 ? () => game.act('click_and_render', 'gemback', idx) : null}/>`)} </div>
      <div className="asset-row bonuses-owned">${safe(player.cards).slice(0, 5).map((count, idx) => html`<div key=${idx} className=${`bonus-stack bonus-${idx}`}><span>${count}</span></div>`)}</div>
      ${safe(player.reserved).length > 0 && html`<div className="reserved-row"><span className="reserved-label">Reserved</span>${player.reserved.map((card, idx) => html`<${Card} key=${`${idx}-${card}`} card=${card} tier=${-1} index=${idx} extra=${game.extra} compact onClick=${current && index === 0 ? () => game.act('click_and_render', 'reserved', idx) : null}/>` )}</div>`}
    </div>
  </article>`;
}

function Settings({ game, open, close }) {
  if (!open) return null;
  return html`<div className="modal-backdrop" onClick=${close}><section className="settings-modal" onClick=${e => e.stopPropagation()}>
    <button className="modal-close" onClick=${close}>×</button><span className="eyebrow">Game setup</span><h2>Shape your match</h2>
    <label>Opponent<select value=${game.arePlayersHuman?.every(Boolean) ? 'Human' : game.arePlayersHuman?.[0] ? 'P0' : 'AI'} onChange=${e => game.setGameMode(e.target.value)}><option value="P0">Play against AI</option><option value="Human">Pass & play</option><option value="AI">Watch AI match</option></select></label>
    <label>AI calculation<select value=${game.numMCTSSims} onChange=${e => { game.numMCTSSims = Number(e.target.value); game.changeDifficulty(); }}><option value="3">Quick</option><option value="12">Balanced</option><option value="25">Strategic</option><option value="100">Master</option><option value="400">Grandmaster</option></select></label>
    <button className="primary-button" onClick=${() => { game.reset(); close(); }}><${Icon} name="reset"/> Start a fresh match</button>
  </section></div>`;
}

function Loading({ game }) {
  return html`<div className="loading-screen"><div className="loader-crown"><${Icon} name="crown" size=${38}/><span></span><span></span><span></span></div><p>${game?.loadingMessage || 'Preparing the table…'}</p><small>The royal court is gathering</small></div>`;
}

function App() {
  const game = useGameStore();
  const [settings, setSettings] = useState(false);
  const [rules, setRules] = useState(false);
  const view = game?.view || {};
  const extra = game?.extra || {};
  const confirmText = useMemo(() => {
    if (!game) return '';
    if (game.gameEnded) return `Player ${safe(game.winners).map(n => n + 1).join(' & ')} wins`;
    if (extra.sel_type === 'none') return 'Choose a card or collect gems';
    return `${extra.can_confirm ? 'Confirm' : 'Cannot'} ${extra.move_desc || 'move'}`;
  }, [game?.gameEnded, game?.winners, extra.sel_type, extra.can_confirm, extra.move_desc]);

  if (!game || game.isLoading || !view.tiers) return html`<${Loading} game=${game}/>`;
  return html`<div className="app-shell">
    <div className="ambient ambient-one"></div><div className="ambient ambient-two"></div>
    <header className="topbar"><a className="brand" href="/"><span className="brand-mark"><${Icon} name="crown" size=${23}/></span><span><b>SPLENDOR</b><small>ROYAL TABLE</small></span></a>
      <div className="turn-pill"><span className=${game.isThinking ? 'thinking' : ''}></span>${game.isThinking ? 'AI is thinking' : game.gameEnded ? 'Match complete' : `${game.currentPlayer === 0 ? 'Your' : `Player ${game.currentPlayer + 1}'s`} turn`}</div>
      <nav><button onClick=${() => setRules(!rules)}>How to play</button><button className="icon-button" onClick=${() => setSettings(true)} aria-label="Settings"><${Icon} name="settings"/></button></nav>
    </header>

    ${rules && html`<aside className="rules-toast"><button onClick=${() => setRules(false)}>×</button><span className="eyebrow">A quick guide</span><strong>Race to 15 prestige</strong><p>Collect gems, purchase developments, and attract nobles. Take 3 different gems or 2 of one color when 4 remain.</p></aside>`}

    <main>
      <section className="hero"><div><span className="eyebrow">A game of Renaissance prestige</span><h1>Build your legacy.</h1><p>Gather rare gems, command trade routes, and earn the favor of nobles.</p></div><div className="hero-stat"><span>Target</span><strong>15</strong><small>prestige</small></div></section>
      <div className="game-layout">
        <section className="board-panel">
          <div className="section-heading"><div><span className="eyebrow">The royal court</span><h2>Nobles</h2></div><span>Earn their visit automatically</span></div>
          <div className="nobles-row">${safe(view.nobles).map((noble, idx) => html`<${Noble} key=${idx} noble=${noble} index=${idx}/>` )}</div>
          <div className="market">${[2, 1, 0].map(tier => html`<div className="market-row" key=${tier} style=${{ '--row-delay': `${(2-tier) * 80}ms` }}>
            <div className="tier-label"><span>Tier</span><strong>${TIER_NAMES[tier]}</strong></div>
            <${Deck} tier=${tier} count=${view.decks?.[tier]} active=${selected(extra, 'deck', items => items[0] === tier)} recent=${lastAction(extra, 'deck', value => value === tier)} onClick=${() => game.act('click_and_render', 'deck', tier)}/>
            <div className="cards-row">${safe(view.tiers[tier]).map((card, idx) => html`<${Card} key=${idx} card=${card} tier=${tier} index=${idx} extra=${extra} onClick=${card?.[0] >= 0 ? () => game.act('click_and_render', 'card', tier, idx) : null}/>` )}</div>
          </div>`)}</div>
          <div className="bank-section"><div className="section-heading compact-heading"><div><span className="eyebrow">Treasury</span><h2>Gem bank</h2></div><span>Choose up to three colors</span></div>
            <div className="bank-row">${safe(view.bank).map((count, idx) => html`<${Gem} key=${idx} index=${idx} count=${count} active=${selected(extra, 'gem', items => items.includes(idx)) ? (extra.sel_items[0] === extra.sel_items[1] ? 'double' : 'active') : ''} recent=${lastAction(extra, 'gem', items => items?.includes(idx))} onClick=${idx < 5 ? () => game.act('click_and_render', 'gem', idx) : null}/>` )}</div>
          </div>
          <div className="action-bar"><button className="undo-button" disabled=${!game.canUndo || game.isThinking} onClick=${() => game.act('undo', game.arePlayersHuman)}><${Icon} name="undo"/> Undo</button>
            <button className=${`confirm-button ${extra.can_confirm || game.gameEnded ? 'ready' : ''}`} disabled=${game.gameEnded ? false : game.isThinking || extra.sel_type === 'none' || !extra.can_confirm} onClick=${() => game.act('confirm_action')}><span>${confirmText}</span><span className="confirm-arrow">→</span></button>
          </div>
        </section>
        <aside className="players-column"><div className="section-heading"><div><span className="eyebrow">At the table</span><h2>Players</h2></div></div>${safe(view.players).map((player, idx) => html`<${PlayerPanel} key=${idx} player=${player} index=${idx} game=${game}/>` )}</aside>
      </div>
    </main>
    <footer><span>Splendor AI</span><span>Crafted for thoughtful play</span></footer>
    <${Settings} game=${game} open=${settings} close=${() => setSettings(false)}/>
  </div>`;
}

const mount = () => {
  const root = document.getElementById('root');
  if (root && !root.dataset.mounted) {
    root.dataset.mounted = 'true';
    ReactDOM.createRoot(root).render(html`<${App}/>`);
  }
};
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
