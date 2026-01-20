/**
 * Hedge Fund Research - Stock Screener
 * Interactive functionality for the screening page
 */

(function() {
    'use strict';

    // ============================================
    // DOM Elements
    // ============================================
    const elements = {
        filterTabs: document.querySelectorAll('.tab'),
        filterGroups: document.querySelectorAll('.filter-group'),
        btnScreen: document.getElementById('btn-screen'),
        btnReset: document.getElementById('btn-reset'),
        btnSave: document.getElementById('btn-save'),
        btnExport: document.getElementById('btn-export'),
        presetSelect: document.getElementById('preset-select'),
        resultsTable: document.getElementById('results-table'),
        viewButtons: document.querySelectorAll('.view-btn'),
        pageButtons: document.querySelectorAll('.page-btn'),
        pageSizeSelect: document.getElementById('page-size')
    };

    // ============================================
    // State
    // ============================================
    const state = {
        activeTab: 'descriptive',
        currentView: 'overview',
        currentPage: 1,
        pageSize: 20,
        sortColumn: 'marketcap',
        sortDirection: 'desc',
        filters: {}
    };

    // ============================================
    // Filter Tab Switching
    // ============================================
    function initFilterTabs() {
        elements.filterTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;

                // Update active tab
                elements.filterTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                // Show/hide filter groups based on tab
                if (tabName === 'all') {
                    elements.filterGroups.forEach(group => {
                        group.style.display = 'block';
                    });
                } else {
                    elements.filterGroups.forEach(group => {
                        if (group.dataset.group === tabName) {
                            group.style.display = 'block';
                        } else {
                            group.style.display = 'none';
                        }
                    });
                }

                state.activeTab = tabName;
            });
        });

        // Initialize - show only descriptive filters
        elements.filterGroups.forEach(group => {
            if (group.dataset.group !== 'descriptive') {
                group.style.display = 'none';
            }
        });
    }

    // ============================================
    // Table Sorting
    // ============================================
    function initTableSorting() {
        const headers = elements.resultsTable.querySelectorAll('th.sortable');

        headers.forEach(header => {
            header.addEventListener('click', () => {
                const column = header.dataset.sort;

                // Toggle sort direction if same column
                if (state.sortColumn === column) {
                    state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    state.sortColumn = column;
                    state.sortDirection = 'desc';
                }

                // Update header classes
                headers.forEach(h => {
                    h.classList.remove('sorted-asc', 'sorted-desc');
                });
                header.classList.add(`sorted-${state.sortDirection}`);

                // Sort the table
                sortTable(column, state.sortDirection);
            });
        });
    }

    function sortTable(column, direction) {
        const tbody = elements.resultsTable.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));

        const columnIndex = {
            'no': 0,
            'ticker': 1,
            'company': 2,
            'sector': 3,
            'marketcap': 4,
            'pe': 5,
            'price': 6,
            'change': 7,
            'volume': 8
        };

        const idx = columnIndex[column];

        rows.sort((a, b) => {
            let aVal = a.cells[idx].textContent.trim();
            let bVal = b.cells[idx].textContent.trim();

            // Parse numeric values
            if (['no', 'marketcap', 'pe', 'price', 'change', 'volume'].includes(column)) {
                aVal = parseNumericValue(aVal);
                bVal = parseNumericValue(bVal);

                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            }

            // String comparison
            return direction === 'asc'
                ? aVal.localeCompare(bVal)
                : bVal.localeCompare(aVal);
        });

        // Re-append sorted rows
        rows.forEach(row => tbody.appendChild(row));

        // Update row numbers
        rows.forEach((row, index) => {
            row.cells[0].textContent = index + 1;
        });
    }

    function parseNumericValue(str) {
        // Remove non-numeric characters except . and -
        let cleaned = str.replace(/[^0-9.\-]/g, '');

        // Handle suffixes (T, B, M, K)
        if (str.includes('T')) {
            return parseFloat(cleaned) * 1000000000000;
        } else if (str.includes('B')) {
            return parseFloat(cleaned) * 1000000000;
        } else if (str.includes('M')) {
            return parseFloat(cleaned) * 1000000;
        } else if (str.includes('K')) {
            return parseFloat(cleaned) * 1000;
        }

        // Handle percentage
        if (str.includes('%')) {
            return parseFloat(cleaned);
        }

        return parseFloat(cleaned) || 0;
    }

    // ============================================
    // View Toggle
    // ============================================
    function initViewToggle() {
        elements.viewButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                elements.viewButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.currentView = btn.dataset.view;

                // In a real app, this would change the table columns
                console.log('View changed to:', state.currentView);
            });
        });
    }

    // ============================================
    // Pagination
    // ============================================
    function initPagination() {
        elements.pageButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                if (btn.disabled) return;

                const pageNum = parseInt(btn.textContent);
                if (!isNaN(pageNum)) {
                    elements.pageButtons.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    state.currentPage = pageNum;

                    // In a real app, this would fetch the next page
                    console.log('Page changed to:', pageNum);
                }
            });
        });

        if (elements.pageSizeSelect) {
            elements.pageSizeSelect.addEventListener('change', (e) => {
                state.pageSize = parseInt(e.target.value);
                state.currentPage = 1;

                // In a real app, this would refetch with new page size
                console.log('Page size changed to:', state.pageSize);
            });
        }
    }

    // ============================================
    // Filter Actions
    // ============================================
    function initFilterActions() {
        // Screen button
        if (elements.btnScreen) {
            elements.btnScreen.addEventListener('click', () => {
                collectFilters();
                runScreen();
            });
        }

        // Reset button
        if (elements.btnReset) {
            elements.btnReset.addEventListener('click', () => {
                resetFilters();
            });
        }

        // Save preset button
        if (elements.btnSave) {
            elements.btnSave.addEventListener('click', () => {
                savePreset();
            });
        }

        // Export button
        if (elements.btnExport) {
            elements.btnExport.addEventListener('click', () => {
                exportResults();
            });
        }

        // Preset select
        if (elements.presetSelect) {
            elements.presetSelect.addEventListener('change', (e) => {
                loadPreset(e.target.value);
            });
        }
    }

    function collectFilters() {
        const filters = {};
        const selects = document.querySelectorAll('.filter-item select');

        selects.forEach(select => {
            if (select.value) {
                const label = select.previousElementSibling?.textContent || select.name;
                filters[label] = select.value;
            }
        });

        state.filters = filters;
        return filters;
    }

    function runScreen() {
        const filters = state.filters;
        const filterCount = Object.keys(filters).length;

        // Show loading state
        elements.btnScreen.disabled = true;
        elements.btnScreen.innerHTML = `
            <svg class="icon spin" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>
            </svg>
            Screening...
        `;

        // Simulate API call
        setTimeout(() => {
            elements.btnScreen.disabled = false;
            elements.btnScreen.innerHTML = `
                <svg class="icon" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/>
                </svg>
                Screen
            `;

            console.log('Screen executed with filters:', filters);

            // In a real app, this would update the table with new results
            showNotification(`Screener applied ${filterCount} filters`);
        }, 500);
    }

    function resetFilters() {
        const selects = document.querySelectorAll('.filter-item select');
        selects.forEach(select => {
            // Reset to first option or default
            const defaultOption = select.querySelector('option[selected]');
            if (defaultOption) {
                select.value = defaultOption.value;
            } else {
                select.selectedIndex = 0;
            }
        });

        state.filters = {};
        showNotification('Filters reset');
    }

    function savePreset() {
        const filters = collectFilters();
        const name = prompt('Enter preset name:');

        if (name) {
            // In a real app, this would save to localStorage or backend
            const presets = JSON.parse(localStorage.getItem('screenerPresets') || '{}');
            presets[name] = filters;
            localStorage.setItem('screenerPresets', JSON.stringify(presets));

            // Add to dropdown
            const option = document.createElement('option');
            option.value = name.toLowerCase().replace(/\s+/g, '_');
            option.textContent = name;
            elements.presetSelect.appendChild(option);

            showNotification(`Preset "${name}" saved`);
        }
    }

    function loadPreset(presetKey) {
        if (!presetKey) return;

        // Predefined presets
        const presets = {
            'momentum': {
                'Index': 'sp500',
                'Performance': 'year_up',
                '200-Day SMA': 'above',
                'P/E': 'under50'
            },
            'social_buzz': {
                'Index': 'sp500',
                'StockTwits Sentiment': 'bullish',
                'Mention Volume': 'high'
            },
            'undervalued': {
                'Index': 'sp500',
                'P/E': 'low',
                'PEG': 'low',
                'ROE': 'over10'
            },
            'breakout': {
                'Index': 'sp500',
                '52W High/Low': 'new_high',
                'Volatility': 'week_over3',
                'Avg Volume': 'over500k'
            }
        };

        const preset = presets[presetKey];
        if (preset) {
            // Reset first
            resetFilters();

            // Apply preset filters
            // In a real app, this would map labels to select elements
            console.log('Loading preset:', presetKey, preset);
            showNotification(`Loaded preset: ${presetKey}`);
        }
    }

    function exportResults() {
        const table = elements.resultsTable;
        const rows = table.querySelectorAll('tbody tr');

        let csv = [];

        // Headers
        const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
        csv.push(headers.join(','));

        // Data rows
        rows.forEach(row => {
            const cells = Array.from(row.querySelectorAll('td')).map(td => {
                let value = td.textContent.trim();
                // Escape commas and quotes
                if (value.includes(',') || value.includes('"')) {
                    value = `"${value.replace(/"/g, '""')}"`;
                }
                return value;
            });
            csv.push(cells.join(','));
        });

        // Download
        const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `screener_results_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showNotification('Results exported to CSV');
    }

    // ============================================
    // Notifications
    // ============================================
    function showNotification(message) {
        // Remove existing notification
        const existing = document.querySelector('.notification');
        if (existing) {
            existing.remove();
        }

        // Create notification element
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            background-color: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-default);
            border-radius: var(--radius-md);
            font-size: var(--font-size-sm);
            z-index: 1000;
            animation: slideIn 0.2s ease;
        `;

        document.body.appendChild(notification);

        // Auto remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.2s ease';
            setTimeout(() => notification.remove(), 200);
        }, 3000);
    }

    // ============================================
    // Keyboard Shortcuts
    // ============================================
    function initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + Enter: Run screen
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                collectFilters();
                runScreen();
            }

            // Ctrl/Cmd + R: Reset filters (prevent page reload)
            if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
                e.preventDefault();
                resetFilters();
            }

            // Ctrl/Cmd + E: Export
            if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
                e.preventDefault();
                exportResults();
            }
        });
    }

    // ============================================
    // Initialize
    // ============================================
    function init() {
        initFilterTabs();
        initTableSorting();
        initViewToggle();
        initPagination();
        initFilterActions();
        initKeyboardShortcuts();

        // Add animation styles
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            .spin {
                animation: spin 1s linear infinite;
            }
        `;
        document.head.appendChild(style);

        console.log('Screener initialized');
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
