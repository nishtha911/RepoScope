import type { FC } from 'react';
import './AppNav.css';

export type Tab = 'OVERVIEW' | 'GRAPH' | 'PR_IMPACT' | 'RAG' | 'RECOMMENDATIONS';

const NAV_ITEMS: { id: Tab; label: string; shortcut: string }[] = [
  { id: 'OVERVIEW', label: 'Overview', shortcut: '1' },
  { id: 'GRAPH', label: 'Symbol Graph', shortcut: '2' },
  { id: 'PR_IMPACT', label: 'PR Impact', shortcut: '3' },
  { id: 'RAG', label: 'Codebase Chat', shortcut: '4' },
  { id: 'RECOMMENDATIONS', label: 'Recommendations', shortcut: '5' },
];

interface Props {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
}

const AppNav: FC<Props> = ({ activeTab, onTabChange }) => {
  return (
    <nav className="app-nav" aria-label="Main navigation">
      <ul className="app-nav__list" role="list">
        {NAV_ITEMS.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <li key={item.id} className="app-nav__item">
              <button
                type="button"
                className={`app-nav__btn${isActive ? ' app-nav__btn--active' : ''}`}
                onClick={() => onTabChange(item.id)}
                aria-pressed={isActive}
                aria-label={`${item.label} (press ${item.shortcut})`}
              >
                {item.label}
                <span className="app-nav__shortcut" aria-hidden="true">
                  {item.shortcut}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};

export default AppNav;

