const { useEffect, useMemo, useState } = React;
const html = htm.bind(React.createElement);

const GEM_NAMES = ['Diamond', 'Sapphire', 'Emerald', 'Ruby', 'Onyx', 'Gold'];
const TIER_NAMES = ['I', 'II', 'III'];

const MOVE_NAMES = {
  buy: 'Purchased development',
  reserve: 'Reserved development',
  gems: 'Collected gems',
  return: 'Returned gems',
  pass: 'Passed'
};

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
          isReplayingAIAction: game.isReplayingAIAction,
          isTimelinePaused: game.isTimelinePaused,
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
const isSubset = (items, option) => items.every((item, index) => {
  const before = items.slice(0, index).filter(value => value === item).length;
  return option.filter(value => value === item).length > before;
});
const canExtendTokenSelection = (items, color, options, goldIsSingle = false) => {
  if (goldIsSingle && color === 5) return options.some(option => option.length === 1 && option[0] === 5);
  const occurrences = items.filter(item => item === color).length;
  if (occurrences && items.length > 1) return true;
  const candidate = occurrences ? [color, color] : [...items, color];
  return options.some(option => candidate.length <= option.length && isSubset(candidate, option));
};

function Icon({ name, size = 20 }) {
  const icons = {
    crown: html`<path d="M3 7l4 4 5-7 5 7 4-4-2 11H5L3 7zM5 21h14"/>`,
    spark: html`<path d="M12 2l1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5L12 2z"/>`,
    undo: html`<path d="M9 7H4v-5M4 7c2.2-2.8 5.4-4 8.6-3 4.4 1.3 6.9 5.9 5.6 10.3-1.3 4.4-5.9 6.9-10.3 5.6-2.5-.7-4.4-2.5-5.4-4.7"/>`,
    reset: html`<path d="M20 6v5h-5M20 11a8 8 0 10-.8 5"/>`,
    settings: html`<path d="M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM19.4 15a1.7 1.7 0 00.3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.6v.2h-4V21a1.7 1.7 0 00-1-1.6 1.7 1.7 0 00-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 00.3-1.9A1.7 1.7 0 003 14H2.8v-4H3a1.7 1.7 0 001.6-1 1.7 1.7 0 00-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 001.9.3A1.7 1.7 0 0010 3v-.2h4V3a1.7 1.7 0 001 1.6 1.7 1.7 0 001.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 00-.3 1.9 1.7 1.7 0 001.6 1h.2v4H21a1.7 1.7 0 00-1.6 1z"/>`,
    user: html`<path d="M20 21a8 8 0 00-16 0M12 13a5 5 0 100-10 5 5 0 000 10z"/>`,
    bot: html`<path d="M12 2v3M8 2h8M5 8h14v11H5zM2 11h3M19 11h3M9 13h.01M15 13h.01M9 17h6"/>`,
    history: html`<path d="M3 12a9 9 0 109-9 9.7 9.7 0 00-6.7 2.7L3 8M3 3v5h5M12 7v5l3 2"/>`
  };
  return html`<svg className="icon" width=${size} height=${size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">${icons[name]}</svg>`;
}

function Gem({ index, count, compact = false, active = '', recent = false, arrival = false, onClick }) {
  return html`<button className=${`gem gem-${index} ${compact ? 'gem-compact' : ''} ${active ? `is-${active}` : ''} ${recent ? 'is-recent' : ''} ${arrival ? 'inventory-arrival' : ''}`} onClick=${onClick} disabled=${!onClick} aria-label=${`${count} ${GEM_NAMES[index]} gems${onClick ? ', select to return' : ''}`}>
    <span className="gem-shine"></span><span className="gem-count">${count}</span><span className="gem-name">${GEM_NAMES[index]}</span>
  </button>`;
}

function Card({ card, tier, index, extra, compact = false, arrival = false, onClick }) {
  if (!card || card[0] < 0) return html`<div className=${`development-card card-empty ${compact ? 'compact' : ''}`}></div>`;
  const [color, points, costs] = card;
  const isMarket = tier >= 0;
  const isBuy = selected(extra, 'card', items => items[0]?.[0] === tier && items[0]?.[1] === index);
  const isReserve = selected(extra, 'rsv', items => items[0]?.[0] === tier && items[0]?.[1] === index);
  const recent = isMarket
    ? (lastAction(extra, 'card', value => value === tier * 4 + index) || lastAction(extra, 'rsv', value => value === tier * 4 + index))
    : lastAction(extra, 'buyrsv', value => value === index);
  return html`<button className=${`development-card color-${color} ${compact ? 'compact' : ''} ${isBuy ? 'is-buy' : ''} ${isReserve ? 'is-reserve' : ''} ${recent ? 'is-recent' : ''} ${arrival ? 'inventory-arrival' : ''}`} onClick=${onClick} disabled=${!onClick} aria-label=${`${GEM_NAMES[color]} card worth ${points} points`}>
    <span className="card-glow"></span>
    <span className="card-top"><strong>${points || ''}</strong><span className=${`bonus bonus-${color}`}></span></span>
    <span className="card-art"><span></span></span>
    <span className="costs">${safe(costs).map(([idx, amount]) => html`<span key=${idx} className=${`cost cost-${idx}`}>${amount}</span>`)}</span>
    ${isReserve && html`<span className="selection-label">Reserve</span>`}
  </button>`;
}

function MarketCard({ card, tier, index, extra, focused, inspect, act, replay }) {
  const options = extra?.card_actions?.[tier]?.[index] || {};
  const isAISource = replay && ['buy', 'reserve'].includes(replay.type) && replay.tier === tier && replay.index === index;
  return html`<div className=${`market-card-shell ${focused ? 'show-actions' : ''} ${isAISource ? 'ai-source-pulse' : ''}`}>
    <${Card} card=${card} tier=${tier} index=${index} extra=${extra} onClick=${card?.[0] >= 0 ? inspect : null}/>
    ${isAISource && replay.card && html`<div className="ai-card-ghost" aria-hidden="true"><${Card} card=${replay.card} tier=${tier} index=${index} extra=${{}}/></div>`}
    ${focused && html`<div className="card-quick-actions" aria-label="Card actions">
      <button className="quick-buy" disabled=${!options.buy} onClick=${event => { event.stopPropagation(); act('buy'); }} title=${options.buy ? 'Purchase this card' : 'Not enough gems to purchase'}><span>◆</span> Buy</button>
      <button className="quick-reserve" disabled=${!options.reserve} onClick=${event => { event.stopPropagation(); act('reserve'); }} title=${options.reserve ? 'Reserve this card' : 'Reserve is unavailable'}><span>◇</span> Hold</button>
    </div>`}
  </div>`;
}

function Noble({ noble, index, arrival = false }) {
  return html`<div className=${`noble ${arrival ? 'inventory-arrival' : ''}`} style=${{ '--delay': `${index * 70}ms` }}>
    <span className="noble-portrait"><${Icon} name="crown" size=${17}/></span>
    <span className="noble-points">3</span>
    <span className="noble-costs">${safe(noble).map(([idx, amount]) => html`<span key=${idx} className=${`mini-cost cost-${idx}`}>${amount}</span>`)}</span>
  </div>`;
}

function Deck({ tier, count, active, recent, onClick, replay }) {
  const isAISource = replay?.type === 'reserve' && replay.tier === tier && replay.index === -1;
  return html`<button className=${`deck tier-${tier} ${active ? 'is-active' : ''} ${recent ? 'is-recent' : ''} ${isAISource ? 'ai-deck-pulse' : ''}`} onClick=${onClick} disabled=${!onClick}>
    <span className="deck-pattern"></span><span className="tier-mark">${TIER_NAMES[tier]}</span><span className="deck-count">${count}<small>cards</small></span>
  </button>`;
}

function PlayerPanel({ player, index, game, inspectReserved, replay }) {
  const human = game.arePlayersHuman?.[index];
  const current = game.currentPlayer === index;
  const reservedCards = safe(player.reserved).map((card, cardIndex) => ({ card, cardIndex })).filter(item => item.card?.[0] >= 0);
  const isThinking = current && !human && game.isThinking && !game.isReplayingAIAction;
  const isActing = replay?.actor === index;
  const overflow = current && (game.extra?.overflow_count || 0) > 0;
  const returnSelection = selected(game.extra, 'gemback') ? safe(game.extra.sel_items) : [];
  const returnOptions = safe(game.extra?.return_options);
  const canReturn = (color, count) => overflow && human && count > 0 && canExtendTokenSelection(returnSelection, color, returnOptions, true);
  const arrivingGems = isActing ? safe(replay?.arriving_gems) : [];
  const arrivingBonus = isActing && replay?.type === 'buy' ? replay.card?.[0] : -1;
  const arrivingReserved = isActing && replay?.type === 'reserve' ? replay.reserved_index : -1;
  const visitorArrived = noble => isActing && safe(replay?.visitors).some(visitor => JSON.stringify(visitor) === JSON.stringify(noble));
  return html`<article className=${`player-panel ${current ? 'is-current' : ''} ${isThinking ? 'is-thinking' : ''} ${isActing ? 'is-acting' : ''} ${overflow ? 'is-returning' : ''}`}>
    <header className="player-header">
      <div className="player-avatar"><${Icon} name=${human ? 'user' : 'bot'} size=${20}/><span className="presence"></span></div>
      <div><p>${index === 0 ? 'You' : human ? `Player ${index + 1}` : `AI ${index + 1}`}</p></div>
      <div className="score"><strong>${player.points}</strong><span>prestige</span></div>
    </header>
    ${overflow && human && html`<div className="overflow-prompt" role="status"><strong>Return ${game.extra.overflow_count} ${game.extra.overflow_count === 1 ? 'token' : 'tokens'}</strong><span>Select an eligible token below to continue your turn.</span></div>`}
    <div className="player-assets">
      <div className="asset-row gems-owned">${safe(player.gems).map((count, idx) => html`<${Gem} key=${idx} index=${idx} count=${count} compact arrival=${arrivingGems?.includes(idx)} active=${selected(game.extra, 'gemback', items => items.includes(idx)) ? (game.extra.sel_items[0] === game.extra.sel_items[1] ? 'double' : 'active') : ''} recent=${lastAction(game.extra, 'gemback', items => items?.includes(idx)) && index === game.extra?.previous_player} onClick=${canReturn(idx, count) ? () => game.act('click_and_render', 'gemback', idx) : null}/>`)} </div>
      <div className="asset-row bonuses-owned">${safe(player.cards).slice(0, 5).map((count, idx) => html`<div key=${idx} className=${`bonus-stack bonus-${idx} ${arrivingBonus === idx ? 'inventory-arrival' : ''}`}><span>${count}</span></div>`)}</div>
      ${reservedCards.length > 0 && html`<div className="reserved-row"><span className="reserved-label">Reserved</span>${reservedCards.map(({ card, cardIndex }) => html`<${Card} key=${`${cardIndex}-${card}`} card=${card} tier=${-1} index=${cardIndex} extra=${game.extra} compact arrival=${cardIndex === arrivingReserved} onClick=${() => inspectReserved(card, index, cardIndex, current && human)}/>` )}</div>`}
      ${safe(player.nobles).length > 0 && html`<div className="player-nobles" aria-label="Visitors"><span className="reserved-label">Visitors</span>${safe(player.nobles).map((noble, nobleIndex) => html`<${Noble} key=${`${nobleIndex}-${noble}`} noble=${noble} index=${nobleIndex} arrival=${visitorArrived(noble)}/>` )}</div>`}
      ${isActing && arrivingGems.length > 0 && html`<div className="inventory-flight inventory-gem-flight" aria-hidden="true">${arrivingGems.map((color, gemIndex) => html`<i key=${`${color}-${gemIndex}`} className=${`gem-${color}`}></i>`)}</div>`}
      ${isActing && replay?.card && ['buy', 'reserve'].includes(replay.type) && html`<div className=${`inventory-flight inventory-card-flight flight-${replay.type}`} aria-hidden="true"><${Card} card=${replay.card} tier=${-1} index=${-1} extra=${{}} compact/></div>`}
      ${isActing && safe(replay?.visitors).length > 0 && html`<div className="inventory-flight inventory-visitor-flight" aria-hidden="true">${safe(replay.visitors).map((visitor, visitorIndex) => html`<${Noble} key=${visitorIndex} noble=${visitor} index=${visitorIndex}/>` )}</div>`}
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


function GemBank({ open, game, start, choose, confirm, close, replay }) {
  const bank = safe(game.view?.bank);
  const isGemSelection = open && game.extra?.sel_type === 'gem';
  const selectedItems = isGemSelection ? safe(game.extra?.sel_items) : [];
  const uniqueCount = new Set(selectedItems).size;
  const isDouble = selectedItems.length === 2 && uniqueCount === 1;
  const ready = isGemSelection && Boolean(game.extra?.can_confirm);
  const takeOptions = safe(game.extra?.take_options);
  const canChoose = color => {
    if (color === 5 || game.extra?.overflow_count > 0) return false;
    if (!open) return takeOptions.some(option => option.includes(color));
    return canExtendTokenSelection(selectedItems, color, takeOptions);
  };
  return html`<section className=${`vertical-gem-bank ${open ? 'is-picking' : ''}`} aria-label=${open ? 'Choose gems from bank' : 'Gem bank'}>
    ${open && html`<div className="vertical-picker-head"><span><small>Current pick</small>${isDouble ? '2 matching' : `${selectedItems.length}/3 colors`}</span><button onClick=${close} aria-label="Cancel gem selection">×</button></div>`}
    <div className="vertical-token-list">${GEM_NAMES.map((name, color) => {
      const occurrences = selectedItems.filter(item => item === color).length;
      const enabled = canChoose(color);
      const isAIActive = ['gems', 'return'].includes(replay?.type) && replay.gems?.includes(color);
      return html`<button key=${color} aria-label=${`${name}: ${bank[color]} available${occurrences ? `, ${occurrences} selected` : ''}`} className=${`token-choice gem-${color} ${occurrences ? 'selected' : ''} ${isAIActive ? 'ai-token-pulse' : ''}`} disabled=${!enabled} onClick=${() => open ? choose(color) : start(color)}>
        <span className="token-stack"><i></i><i></i><i></i><b>${bank[color]}</b></span>
        ${occurrences > 0 && html`<em>+${occurrences}</em>`}
      </button>`;
    })}</div>
    ${open && html`<div className="vertical-picker-actions"><button onClick=${close}>Cancel</button><button disabled=${!ready || game.isThinking} onClick=${confirm}>Take gems <span>→</span></button></div>`}
  </section>`;
}
function ReservedCardDialog({ focus, game, choose, close }) {
  if (!focus) return null;
  const { card, playerIndex, cardIndex, canBuy } = focus;
  const buyAvailable = Boolean(canBuy && game.extra?.reserved_actions?.[cardIndex]);
  return html`<section className="reserved-inspector" aria-label=${`Player ${playerIndex + 1} reserved card`}>
    <div className="reserved-inspector-head"><span><small>Player ${playerIndex + 1}</small>Reserved card</span><button onClick=${close} aria-label="Close reserved card">×</button></div>
    <div className="reserved-inspector-body">
      <${Card} card=${card} tier=${-1} index=${cardIndex} extra=${game.extra}/>
      ${canBuy && html`<button className="reserved-buy" disabled=${!buyAvailable} onClick=${choose}>${buyAvailable ? 'Buy' : 'Can’t buy'}</button>`}
    </div>
  </section>`;
}

function ActionReplay({ event, game }) {
  if (!event) return null;
  const human = game.arePlayersHuman?.[event.actor];
  const actor = human ? (event.actor === 0 ? 'You' : `Player ${event.actor + 1}`) : `AI ${event.actor + 1}`;
  const displayedGems = event.type === 'return' ? safe(event.gems) : safe(event.arriving_gems).length ? event.arriving_gems : safe(event.gems);
  return html`<div className=${`ai-action-replay replay-${event.type}`} role="status" aria-live="polite">
    <div className="replay-actor"><span><${Icon} name=${human ? 'user' : 'bot'} size=${16}/></span><strong>${actor}</strong></div>
    <div className="replay-motion">
      ${safe(event.visitors).length > 0 && html`<span className="replay-visitor" aria-hidden="true"><${Icon} name="crown" size=${17}/></span>`}
      ${event.card && html`<div className="replay-card" aria-hidden="true"><${Card} card=${event.card} tier=${event.tier} index=${event.index} extra=${{}} compact/></div>`}
      ${displayedGems.length > 0 && html`<div className="replay-gems">${displayedGems.map((color, index) => html`<i key=${`${color}-${index}`} className=${`gem-${color}`}></i>`)}</div>`}
      ${event.type === 'reserve' && !event.card && html`<span className="replay-deck">${TIER_NAMES[event.tier] || 'I'}</span>`}
      ${event.type === 'pass' && html`<span className="replay-pass">—</span>`}
      <span className="replay-trail"><i></i><i></i><i></i></span>
    </div>
    <b>${event.label}${safe(event.visitors).length > 0 ? ' · visitor arrived' : ''}</b>
  </div>`;
}

function actorName(_game, actor) {
  return `Player ${actor + 1}`;
}

function gemDescription(gems) {
  const counts = safe(gems).reduce((totals, color) => {
    totals[color] = (totals[color] || 0) + 1;
    return totals;
  }, {});
  return Object.entries(counts).map(([color, count]) => `${count} ${GEM_NAMES[color] || 'unknown'}${count > 1 ? ' gems' : ' gem'}`).join(', ');
}

function cardDescription(event) {
  if (!event.card) return event.tier >= 0 ? `Face-down tier ${TIER_NAMES[event.tier] || event.tier} development` : '';
  const [color, points, costs] = event.card;
  const cost = safe(costs).map(([gem, amount]) => `${amount} ${GEM_NAMES[gem] || 'unknown'}`).join(', ');
  return [
    event.tier >= 0 ? `Tier ${TIER_NAMES[event.tier] || event.tier}` : 'Reserved',
    `${GEM_NAMES[color] || 'Unknown'} development`,
    `${points || 0} prestige`,
    cost ? `cost ${cost}` : 'free'
  ].join(' · ');
}

function TurnHistory({ game, open, close }) {
  const events = safe(game.extra?.turn_log);
  const rewindDisabled = game.isThinking && !game.isReplayingAIAction;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = event => {
      if (event.key === 'Escape') {
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      const drawer = document.getElementById('turn-history-drawer');
      const focusable = [...(drawer?.querySelectorAll('button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])') || [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, close]);

  useEffect(() => {
    if (!open || !game.isTimelinePaused) return;
    const timer = setTimeout(() => document.querySelector('.history-paused button')?.focus(), 0);
    return () => clearTimeout(timer);
  }, [open, game.isTimelinePaused, events.length]);

  if (!open) return null;
  return html`<div className="history-backdrop" onClick=${close}>
    <aside id="turn-history-drawer" className="history-drawer" role="dialog" aria-modal="true" aria-labelledby="history-title" onClick=${event => event.stopPropagation()}>
      <header className="history-header">
        <div><span className="eyebrow">The royal record</span><h2 id="history-title">Turn history</h2></div>
        <button className="history-close" onClick=${close} aria-label="Close turn history" autoFocus>×</button>
      </header>
      ${game.isTimelinePaused && html`<div className="history-paused" role="status">
        <div><strong>Viewing earlier position</strong><span>Continue here to create a new branch.</span></div>
        <button onClick=${() => game.resumeTimeline()}>Resume</button>
      </div>`}
      ${rewindDisabled && html`<p className="history-thinking" role="status">History controls are available when the AI finishes calculating.</p>`}
      <div className="history-scroll">
        ${events.length === 0 ? html`<div className="history-empty"><${Icon} name="history" size=${25}/><strong>No moves recorded yet</strong><p>Your completed turns will appear here.</p></div>` : html`
          <ol className="history-list" aria-label="Moves, newest first">
            ${events.map(event => {
              const arrivalDetail = event.type === 'reserve' && safe(event.arriving_gems).length ? ` · Gained ${gemDescription(event.arriving_gems)}` : '';
              const moveDetail = `${['buy', 'reserve'].includes(event.type) ? cardDescription(event) : ['gems', 'return'].includes(event.type) ? gemDescription(event.gems) : ''}${arrivalDetail}${safe(event.visitors).length ? ' · Visitor arrived' : ''}`;
              const movesBack = Number(event.moves_back) || 0;
              return html`<li key=${event.id} className="history-entry">
                <div className="history-entry-head">
                  <span className="history-actor"><${Icon} name="history" size=${14}/>${actorName(game, event.actor)}</span>
                  <span className="history-position">${movesBack === 0 ? 'Latest move' : `${movesBack} move${movesBack === 1 ? '' : 's'} back`}</span>
                </div>
                <div className="history-entry-body">
                  <strong>${event.label || MOVE_NAMES[event.type] || 'Completed a move'}</strong>
                  <span className="history-type">${MOVE_NAMES[event.type] || event.type}</span>
                  ${moveDetail && html`<p>${moveDetail}</p>`}
                </div>
                <button className="history-rewind" disabled=${rewindDisabled} onClick=${async () => {
                  await game.rewind(event.offset);
                  requestAnimationFrame(() => document.querySelector('.history-paused button, .history-close')?.focus());
                }} aria-label=${`Rewind to before ${actorName(game, event.actor)} ${event.label || MOVE_NAMES[event.type] || 'made this move'}`}>
                  <${Icon} name="undo" size=${15}/> Rewind before move
                </button>
              </li>`;
            })}
          </ol>`}
      </div>
    </aside>
  </div>`;
}

function Loading({ game }) {
  return html`<div className="loading-screen"><div className="loader-crown"><${Icon} name="crown" size=${38}/><span></span><span></span><span></span></div><p>${game?.loadingMessage || 'Preparing the table…'}</p><small>The royal court is gathering</small></div>`;
}

function App() {
  const game = useGameStore();
  const [settings, setSettings] = useState(false);
  const [history, setHistory] = useState(false);
  const [rules, setRules] = useState(false);
  const [cardFocus, setCardFocus] = useState(null);
  const [gemPicker, setGemPicker] = useState(false);
  const [reservedFocus, setReservedFocus] = useState(null);
  const [actionReplay, setActionReplay] = useState(null);
  const view = game?.view || {};
  const extra = game?.extra || {};
  const overflow = extra.overflow_count || 0;
  const confirmText = useMemo(() => {
    if (!game) return '';
    if (game.gameEnded) return `Player ${safe(game.winners).map(n => n + 1).join(' & ')} wins`;
    if (overflow > 0 && extra.sel_type !== 'gemback') return `Return ${overflow} ${overflow === 1 ? 'token' : 'tokens'} to continue`;
    if (extra.sel_type === 'gemback') return `${extra.can_confirm ? 'Return' : 'Cannot return'} ${safe(extra.sel_items).length} ${safe(extra.sel_items).length === 1 ? 'token' : 'tokens'}`;
    if (extra.sel_type === 'none') return 'Choose a card or collect gems';
    if (extra.sel_type === 'gem') return `${extra.can_confirm ? 'Take' : 'Cannot take'} ${safe(extra.sel_items).length} ${safe(extra.sel_items).length === 1 ? 'token' : 'tokens'}`;
    return `${extra.can_confirm ? 'Confirm' : 'Cannot'} ${extra.move_desc || 'move'}`;
  }, [game?.gameEnded, game?.winners, overflow, extra.sel_type, extra.sel_items, extra.can_confirm, extra.move_desc]);

  useEffect(() => {
    const event = extra.action_event;
    if (!event) {
      setActionReplay(null);
      return;
    }
    setActionReplay(event);
    const timer = setTimeout(() => setActionReplay(null), globalThis.actionAnimationDuration || 1900);
    return () => clearTimeout(timer);
  }, [extra.action_event?.id]);

  const openCardFlow = async (card, tier, index) => {
    if (extra.overflow_count > 0) return;
    if (extra.sel_type !== 'none') await game.act('clear_selection');
    setGemPicker(false);
    setReservedFocus(null);
    setCardFocus(current => current?.tier === tier && current?.index === index ? null : { card, tier, index });
  };
  const runCardAction = async mode => {
    if (!cardFocus) return;
    if (extra.overflow_count > 0) return;
    const available = extra.card_actions?.[cardFocus.tier]?.[cardFocus.index]?.[mode];
    if (!available) return;
    await game.act('select_card_action', mode, cardFocus.tier, cardFocus.index);
    await game.act('confirm_action');
    setCardFocus(null);
  };
  const openGemPicker = async color => {
    if (extra.overflow_count > 0) return;
    if (extra.sel_type !== 'gem') await game.act('clear_selection');
    setCardFocus(null);
    setReservedFocus(null);
    setGemPicker(true);
    await game.act('click_and_render', 'gem', color);
  };
  const closeGemPicker = async () => {
    await game.act('clear_selection');
    setGemPicker(false);
  };
  const confirmGemSelection = async () => {
    if (!game.extra?.can_confirm) return;
    await game.act('confirm_action');
    setGemPicker(false);
  };
  const inspectReserved = async (card, playerIndex, cardIndex, canBuy) => {
    if (extra.overflow_count > 0) return;
    if (extra.sel_type !== 'none') await game.act('clear_selection');
    setCardFocus(null);
    setGemPicker(false);
    setReservedFocus({ card, playerIndex, cardIndex, canBuy });
  };
  const chooseReservedCard = async () => {
    if (!reservedFocus || !extra.reserved_actions?.[reservedFocus.cardIndex]) return;
    await game.act('select_card_action', 'buy', -1, reservedFocus.cardIndex);
    await game.act('confirm_action');
    setReservedFocus(null);
  };
  const closeReserved = () => setReservedFocus(null);
  const closeHistory = () => {
    setHistory(false);
    requestAnimationFrame(() => document.querySelector('.history-trigger')?.focus());
  };

  if (!game || game.isLoading || !view.tiers) return html`<${Loading} game=${game}/>`;
  return html`<div className="app-shell">
    <div className="ambient ambient-one"></div><div className="ambient ambient-two"></div>
    <header className="topbar"><a className="brand" href="/"><span className="brand-mark"><${Icon} name="crown" size=${23}/></span><span><b>SPLENDOR</b><small>ROYAL TABLE</small></span></a>
      <nav><button onClick=${() => setRules(!rules)}>How to play</button><button className="icon-button" onClick=${() => setSettings(true)} aria-label="Settings"><${Icon} name="settings"/></button></nav>
    </header>

    ${rules && html`<aside className="rules-toast"><button onClick=${() => setRules(false)}>×</button><span className="eyebrow">A quick guide</span><strong>Race to 15 prestige</strong><p>Collect gems, purchase developments, and attract nobles. Take 3 different gems or 2 of one color when 4 remain.</p></aside>`}

    <main className="table-main">
      <div className="game-statusbar">
        <span>Target <strong>15</strong></span>
        <span>Turn <strong>${game.currentPlayer + 1}</strong></span>
        ${game.isTimelinePaused && html`<div className="timeline-viewing" role="status"><strong>Viewing earlier position</strong><button onClick=${() => game.resumeTimeline()}>Resume</button></div>`}
        ${game.isThinking && !game.isReplayingAIAction && html`<b>Thinking…</b>`}
        <button className="history-trigger" onClick=${() => setHistory(true)} aria-haspopup="dialog" aria-expanded=${history} aria-controls="turn-history-drawer">
          <${Icon} name="history" size=${16}/> History${safe(extra.turn_log).length > 0 && html`<span>${safe(extra.turn_log).length}</span>`}
        </button>
      </div>
      <${ActionReplay} event=${actionReplay} game=${game}/>
      <div className="table-layout">
        <aside className="players-column table-players">
          <${ReservedCardDialog} focus=${reservedFocus} game=${game} choose=${chooseReservedCard} close=${closeReserved}/>
          ${safe(view.players).map((player, idx) => html`<${PlayerPanel} key=${idx} player=${player} index=${idx} game=${game} inspectReserved=${inspectReserved} replay=${actionReplay}/>` )}
        </aside>
        <section className="bank-column">
          <span className="column-label">Bank</span>
          <${GemBank} open=${gemPicker} game=${game} start=${openGemPicker} choose=${color => game.act('click_and_render', 'gem', color)} confirm=${confirmGemSelection} close=${closeGemPicker} replay=${actionReplay}/>
        </section>
        <section className="board-panel table-board">
          <div className="nobles-row" tabIndex="0" aria-label="Available nobles">${safe(view.nobles).map((noble, idx) => html`<${Noble} key=${idx} noble=${noble} index=${idx}/>` )}</div>
          <div className="market">${[2, 1, 0].map(tier => html`<div className="market-row" key=${tier}>
            <div className="tier-label"><strong>${TIER_NAMES[tier]}</strong></div>
            <${Deck} tier=${tier} count=${view.decks?.[tier]} active=${selected(extra, 'deck', items => items[0] === tier)} recent=${lastAction(extra, 'deck', value => value === tier)} replay=${actionReplay} onClick=${extra.overflow_count > 0 ? null : async () => { setCardFocus(null); setGemPicker(false); setReservedFocus(null); await game.act('click_and_render', 'deck', tier); }}/>
            <div className="cards-row">${safe(view.tiers[tier]).map((card, idx) => html`<${MarketCard} key=${idx} card=${card} tier=${tier} index=${idx} extra=${extra} focused=${extra.overflow_count > 0 ? false : cardFocus?.tier === tier && cardFocus?.index === idx} inspect=${extra.overflow_count > 0 ? null : () => openCardFlow(card, tier, idx)} act=${runCardAction} replay=${actionReplay}/>` )}</div>
          </div>`)}</div>
          <div className="action-bar"><button className="undo-button" aria-label="Undo last move" disabled=${!game.canUndo || game.isThinking} onClick=${() => game.act('undo', game.arePlayersHuman)}><${Icon} name="undo"/></button>
            <button className=${`confirm-button ${extra.can_confirm || game.gameEnded ? 'ready' : ''}`} disabled=${game.gameEnded ? false : game.isThinking || extra.sel_type === 'none' || !extra.can_confirm} onClick=${gemPicker ? confirmGemSelection : () => game.act('confirm_action')}><span>${confirmText}</span><span className="confirm-arrow">→</span></button>
          </div>
        </section>
      </div>
    </main>
    <${Settings} game=${game} open=${settings} close=${() => setSettings(false)}/>
    <${TurnHistory} game=${game} open=${history} close=${closeHistory}/>
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
