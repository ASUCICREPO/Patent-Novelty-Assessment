/**
 * State persistence utilities for handling page refresh scenarios
 * Maintains search state across page refreshes without changing execution flow
 */

export interface SearchState {
  hasTriggered: boolean;
  isSearching: boolean;
  searchStartTime: number;
  lastPollTime: number;
  retryCount: number;
  error: string | null;
  results: any[];
}

export interface ReportGenerationState {
  hasTriggered: boolean;
  isGenerating: boolean;
  generationStartTime: number;
  lastPollTime: number;
  error: string | null;
  reportsReady: {
    ptlsReady: boolean;
    ecaReady: boolean;
  };
}

export interface SearchStateManager {
  getState: (key: string) => SearchState | null;
  setState: (key: string, state: Partial<SearchState>) => void;
  clearState: (key: string) => void;
  isSearchInProgress: (key: string) => boolean;
  shouldResumeSearch: (key: string) => boolean;
}

export interface ReportStateManager {
  getReportState: (key: string) => ReportGenerationState | null;
  setReportState: (key: string, state: Partial<ReportGenerationState>) => void;
  clearReportState: (key: string) => void;
  isReportGenerationInProgress: (key: string) => boolean;
  shouldResumeReportGeneration: (key: string) => boolean;
}

class StatePersistenceManager implements SearchStateManager, ReportStateManager {
  private readonly STORAGE_PREFIX = 'patent_search_';
  private readonly REPORT_PREFIX = 'report_generation_';
  private readonly SEARCH_TIMEOUT = 10 * 60 * 1000; // 10 minutes
  private readonly REPORT_TIMEOUT = 60 * 60 * 1000; // 60 minutes (very long timeout)

  /**
   * Get search state from localStorage
   */
  getState(key: string): SearchState | null {
    if (typeof window === 'undefined') return null;
    
    try {
      const stored = localStorage.getItem(`${this.STORAGE_PREFIX}${key}`);
      if (!stored) return null;
      
      const state = JSON.parse(stored) as SearchState;
      
      // Check if search has timed out
      const now = Date.now();
      if (state.searchStartTime && (now - state.searchStartTime) > this.SEARCH_TIMEOUT) {
        this.clearState(key);
        return null;
      }
      
      return state;
    } catch (error) {
      console.error('Error reading search state:', error);
      return null;
    }
  }

  /**
   * Set search state in localStorage
   */
  setState(key: string, state: Partial<SearchState>): void {
    if (typeof window === 'undefined') return;
    
    try {
      const existing = this.getState(key) || this.getDefaultState();
      const newState = { ...existing, ...state };
      localStorage.setItem(`${this.STORAGE_PREFIX}${key}`, JSON.stringify(newState));
    } catch (error) {
      console.error('Error saving search state:', error);
    }
  }

  /**
   * Clear search state from localStorage
   */
  clearState(key: string): void {
    if (typeof window === 'undefined') return;
    
    try {
      localStorage.removeItem(`${this.STORAGE_PREFIX}${key}`);
    } catch (error) {
      console.error('Error clearing search state:', error);
    }
  }

  /**
   * Check if search is currently in progress
   */
  isSearchInProgress(key: string): boolean {
    const state = this.getState(key);
    if (!state) return false;
    
    const now = Date.now();
    const timeSinceStart = now - state.searchStartTime;
    const timeSinceLastPoll = now - state.lastPollTime;
    
    // Search is in progress if:
    // 1. It was triggered and not completed
    // 2. It's within timeout period
    // 3. Last poll was recent (within 2 minutes)
    return state.hasTriggered && 
           state.isSearching && 
           timeSinceStart < this.SEARCH_TIMEOUT &&
           timeSinceLastPoll < 2 * 60 * 1000; // 2 minutes
  }

  /**
   * Check if search should be resumed (triggered but not completed)
   */
  shouldResumeSearch(key: string): boolean {
    const state = this.getState(key);
    if (!state) return false;
    
    const now = Date.now();
    const timeSinceStart = now - state.searchStartTime;
    
    // Should resume if:
    // 1. Search was triggered
    // 2. It's within timeout period
    // 3. No results yet or search was interrupted
    return state.hasTriggered && 
           timeSinceStart < this.SEARCH_TIMEOUT &&
           (state.results.length === 0 || state.isSearching);
  }

  /**
   * Get default search state
   */
  private getDefaultState(): SearchState {
    return {
      hasTriggered: false,
      isSearching: false,
      searchStartTime: 0,
      lastPollTime: 0,
      retryCount: 0,
      error: null,
      results: []
    };
  }

  // ===== REPORT GENERATION STATE MANAGEMENT =====

  /**
   * Get report generation state from localStorage
   */
  getReportState(key: string): ReportGenerationState | null {
    if (typeof window === 'undefined') return null;
    
    try {
      const stored = localStorage.getItem(`${this.REPORT_PREFIX}${key}`);
      if (!stored) return null;
      
      const state = JSON.parse(stored) as ReportGenerationState;
      
      // Check if report generation has timed out
      const now = Date.now();
      if (state.generationStartTime && (now - state.generationStartTime) > this.REPORT_TIMEOUT) {
        this.clearReportState(key);
        return null;
      }
      
      return state;
    } catch (error) {
      console.error('Error reading report generation state:', error);
      return null;
    }
  }

  /**
   * Set report generation state in localStorage
   */
  setReportState(key: string, state: Partial<ReportGenerationState>): void {
    if (typeof window === 'undefined') return;
    
    try {
      const existing = this.getReportState(key) || this.getDefaultReportState();
      const newState = { ...existing, ...state };
      localStorage.setItem(`${this.REPORT_PREFIX}${key}`, JSON.stringify(newState));
    } catch (error) {
      console.error('Error saving report generation state:', error);
    }
  }

  /**
   * Clear report generation state from localStorage
   */
  clearReportState(key: string): void {
    if (typeof window === 'undefined') return;
    
    try {
      localStorage.removeItem(`${this.REPORT_PREFIX}${key}`);
    } catch (error) {
      console.error('Error clearing report generation state:', error);
    }
  }

  /**
   * Check if report generation is in progress
   */
  isReportGenerationInProgress(key: string): boolean {
    const state = this.getReportState(key);
    return state ? state.isGenerating : false;
  }

  /**
   * Check if report generation should be resumed
   */
  shouldResumeReportGeneration(key: string): boolean {
    const state = this.getReportState(key);
    if (!state) return false;
    
    const now = Date.now();
    const timeSinceStart = now - state.generationStartTime;
    
    // Should resume if:
    // 1. Generation was triggered
    // 2. It's within timeout period
    // 3. Not both reports ready or generation was interrupted
    return state.hasTriggered && 
           timeSinceStart < this.REPORT_TIMEOUT &&
           (!state.reportsReady.ptlsReady || !state.reportsReady.ecaReady || state.isGenerating);
  }

  /**
   * Get default report generation state
   */
  private getDefaultReportState(): ReportGenerationState {
    return {
      hasTriggered: false,
      isGenerating: false,
      generationStartTime: 0,
      lastPollTime: 0,
      error: null,
      reportsReady: {
        ptlsReady: false,
        ecaReady: false
      }
    };
  }
}

// Export singleton instance
export const statePersistence = new StatePersistenceManager();
