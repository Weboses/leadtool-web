/**
 * Lead-Tool V4.0 - Web Edition
 * Frontend JavaScript
 */

// State
let state = {
    currentProject: null,
    currentPage: 1,
    perPage: 50,
    totalPages: 1,
    totalLeads: 0,  // Gesamtzahl aller Leads (für Auswahl-Buttons)
    selectedIds: new Set(),
    currentTask: null,
    leads: [],
    originalColumns: [],  // Original CSV-Spalten für dynamische Tabelle
    currentFilter: null,  // 'no_names', 'no_compliment', 'complete', null
    currentLeadId: null   // Für Lead-Modal
};

// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initUpload();
    initSearch();
    initTableScroll();  // Scroll-Tracking für Tabelle
    loadProjects();  // Projekte-Dropdown laden
    loadLeads();
    loadApiConfig();
});

// Scroll-Tracking für Tabelle (zeigt Scroll-Indikator)
function initTableScroll() {
    const container = document.getElementById('tableContainer');
    if (!container) return;

    container.addEventListener('scroll', () => {
        // Prüfe ob ganz unten gescrollt
        const isAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 5;
        container.classList.toggle('scrolled-bottom', isAtBottom);

        // Scroll-Hinweis verstecken wenn gescrollt
        const scrollHint = document.getElementById('scrollHint');
        if (scrollHint && container.scrollTop > 50) {
            scrollHint.style.display = 'none';
        }
    });
}

// ============================================================
// NAVIGATION
// ============================================================
function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            switchView(view);
        });
    });
}

function switchView(viewName) {
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    // Update views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.toggle('active', view.id === viewName + 'View');
    });

    // Load data for specific views
    if (viewName === 'prompts') loadPrompts();
    if (viewName === 'api') loadApiConfig();
    if (viewName === 'settings') loadSettingsInfo();
}

// ============================================================
// LEADS
// ============================================================
async function loadLeads() {
    const projectId = document.getElementById('projectSelect').value;
    const search = document.getElementById('searchInput').value;

    try {
        const params = new URLSearchParams({
            page: state.currentPage,
            per_page: state.perPage,
            ...(projectId && { project_id: projectId }),
            ...(search && { search: search }),
            ...(state.currentFilter && { filter: state.currentFilter }),
            ...(state.categoryFilter && { category: state.categoryFilter }),
            ...(state.minRating && { min_rating: state.minRating }),
            ...(state.minReviews && { min_reviews: state.minReviews })
        });

        console.log('loadLeads: Fetching with params:', params.toString());

        const response = await fetch(`/api/leads?${params}`);
        const data = await response.json();

        console.log('loadLeads: API returned', {
            leads: data.leads ? data.leads.length : 0,
            total: data.total,
            pages: data.pages,
            original_columns: data.original_columns ? data.original_columns.length : 0
        });

        state.leads = data.leads || [];
        state.totalPages = data.pages || 1;
        state.totalLeads = data.total || 0;
        state.currentProject = projectId || null;

        // Original-Spalten speichern und Tabellen-Header bauen
        if (data.original_columns && Array.isArray(data.original_columns) && data.original_columns.length > 0) {
            state.originalColumns = data.original_columns;
            renderTableHeader(data.original_columns);
            console.log('loadLeads: Set originalColumns:', data.original_columns.length, 'columns');
        } else {
            // Falls keine Spalten vorhanden, leeres Array setzen
            if (!state.originalColumns) {
                state.originalColumns = [];
            }
            console.log('loadLeads: No original_columns in response, using existing:', state.originalColumns.length);
        }

        renderLeadsTable(data.leads || []);
        updatePagination(data);
        updateCounts(data.total || 0);
        updateFilterButtons();
    } catch (error) {
        showToast('Fehler beim Laden der Leads', 'error');
        console.error('loadLeads error:', error);
    }
}

// Dynamischen Tabellen-Header bauen
function renderTableHeader(columns) {
    const thead = document.getElementById('leadsTableHead');
    const tr = document.createElement('tr');

    // Feste Spalten am Anfang: Checkbox, Nr, Vorname, Nachname, Kompliment
    tr.innerHTML = `
        <th class="checkbox-col">
            <input type="checkbox" id="selectAllCheckbox" onchange="toggleAllOnPage()">
        </th>
        <th class="nr-col">Nr.</th>
        <th class="name-col">Vorname</th>
        <th class="name-col">Nachname</th>
        <th class="compliment-col">Kompliment</th>
    `;

    // Alle Original-CSV-Spalten hinzufügen
    columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col;
        th.title = col;  // Tooltip für lange Namen
        tr.appendChild(th);
    });

    thead.innerHTML = '';
    thead.appendChild(tr);
}

function renderLeadsTable(leads) {
    const tbody = document.getElementById('leadsTableBody');
    if (!tbody) {
        console.error('renderLeadsTable: tbody not found!');
        return;
    }
    tbody.innerHTML = '';

    // Sicherheitscheck für leads
    if (!leads || !Array.isArray(leads)) {
        console.error('renderLeadsTable: leads ist kein Array:', leads);
        return;
    }

    console.log(`renderLeadsTable: Rendering ${leads.length} leads`);

    // Berechne die Start-Nummer für diese Seite
    const startNum = ((state.currentPage - 1) * state.perPage) + 1;

    // Sicherstellen dass originalColumns ein Array ist
    const columns = state.originalColumns || [];

    leads.forEach((lead, index) => {
        try {
            const rowNum = startNum + index;
            const tr = document.createElement('tr');
            tr.dataset.leadId = lead.id;

            // Feste Spalten am Anfang
            let html = `
                <td class="checkbox-col">
                    <input type="checkbox"
                        data-id="${lead.id}"
                        ${state.selectedIds.has(lead.id) ? 'checked' : ''}
                        onchange="toggleSelection(${lead.id}, this.checked)">
                </td>
                <td class="nr-col">${rowNum}</td>
                <td class="${lead.first_name ? 'name-found' : 'name-missing'}">
                    ${escapeHtml(lead.first_name || '-')}
                </td>
                <td class="${lead.last_name ? 'name-found' : 'name-missing'}">
                    ${escapeHtml(lead.last_name || '-')}
                </td>
                <td class="compliment-cell ${lead.compliment ? 'has-compliment' : ''}" title="${escapeHtml(lead.compliment || '')}">
                    ${lead.compliment ? truncate(lead.compliment, 40) : '-'}
                </td>
            `;

            // Alle Original-CSV-Spalten hinzufügen
            const originalData = lead.original_data || {};
            columns.forEach(col => {
                try {
                    const rawValue = originalData[col];
                    const value = (rawValue !== null && rawValue !== undefined) ? String(rawValue) : '';
                    const displayValue = truncate(value, 50);

                    // Spezielle Formatierung für bestimmte Spaltentypen
                    const colLower = col.toLowerCase();
                    if (colLower.includes('site') || colLower.includes('url') || colLower === 'website') {
                        if (value) {
                            const url = value.startsWith('http') ? value : 'https://' + value;
                            html += `<td><a href="${escapeHtml(url)}" target="_blank" class="website-link" onclick="event.stopPropagation()">${escapeHtml(displayValue)}</a></td>`;
                        } else {
                            html += `<td>-</td>`;
                        }
                    } else if (colLower.includes('email')) {
                        html += `<td class="email-cell">${escapeHtml(displayValue) || '-'}</td>`;
                    } else if (colLower === 'rating') {
                        html += `<td class="rating-cell">${value ? '⭐ ' + escapeHtml(value) : '-'}</td>`;
                    } else {
                        html += `<td title="${escapeHtml(value)}">${escapeHtml(displayValue) || '-'}</td>`;
                    }
                } catch (colError) {
                    console.error(`Error rendering column ${col} for lead ${lead.id}:`, colError);
                    html += `<td>-</td>`;
                }
            });

            tr.innerHTML = html;

            // Doppelklick öffnet Lead-Details
            tr.addEventListener('dblclick', () => openLeadModal(lead.id));
            tbody.appendChild(tr);
        } catch (rowError) {
            console.error(`Error rendering lead ${index}:`, rowError, lead);
        }
    });

    console.log(`renderLeadsTable: Finished rendering, tbody has ${tbody.children.length} rows`);

    // DEBUG: Zeige Anzahl gerenderte Zeilen in der Konsole und als Attribut
    tbody.setAttribute('data-rendered-count', tbody.children.length);

    // Prüfe ob alle Zeilen tatsächlich da sind
    if (tbody.children.length !== leads.length) {
        console.warn(`WARNING: Expected ${leads.length} rows but got ${tbody.children.length}`);
    }

    // Scroll-Info aktualisieren
    updateScrollInfo();
}

// Zeigt Hinweis an wenn mehr Zeilen vorhanden sind als sichtbar
function updateScrollInfo() {
    const container = document.getElementById('tableContainer');
    const tbody = document.getElementById('leadsTableBody');
    if (!container || !tbody) return;

    // Nach kurzer Verzögerung prüfen (DOM muss fertig sein)
    setTimeout(() => {
        const rowCount = tbody.children.length;
        const canScroll = container.scrollHeight > container.clientHeight;

        // Scroll-Hinweis anzeigen/verstecken
        let scrollHint = document.getElementById('scrollHint');
        if (rowCount > 0 && canScroll) {
            if (!scrollHint) {
                scrollHint = document.createElement('div');
                scrollHint.id = 'scrollHint';
                scrollHint.className = 'scroll-hint';
                scrollHint.textContent = '↓ Scrollen für mehr Leads';
                container.parentNode.insertBefore(scrollHint, container.nextSibling);
            }
            scrollHint.style.display = 'block';
        } else if (scrollHint) {
            scrollHint.style.display = 'none';
        }
    }, 100);
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

// ECHTZEIT-UPDATE: Einzelne Zeile aktualisieren ohne komplette Tabelle neu zu laden
// Feste Spalten-Indizes (dynamische Spalten kommen danach):
// 0=Checkbox, 1=Nr, 2=Vorname, 3=Nachname, 4=Kompliment, 5+...=Original-CSV-Spalten
function updateTableRow(updatedData) {
    const row = document.querySelector(`tr[data-lead-id="${updatedData.id}"]`);
    if (!row) return;

    const cells = row.querySelectorAll('td');

    // Namen aktualisieren (Vorname=2, Nachname=3)
    if (updatedData.first_name !== undefined) {
        if (cells[2]) {
            cells[2].textContent = updatedData.first_name || '-';
            cells[2].className = updatedData.first_name ? 'name-found' : 'name-missing';
        }
        if (cells[3]) {
            cells[3].textContent = updatedData.last_name || '-';
            cells[3].className = updatedData.last_name ? 'name-found' : 'name-missing';
        }
        // Visuelles Feedback - kurz aufleuchten
        row.style.transition = 'background-color 0.3s';
        row.style.backgroundColor = 'rgba(16, 185, 129, 0.3)';
        setTimeout(() => {
            row.style.backgroundColor = '';
        }, 1000);
    }

    // Kompliment aktualisieren (Index=4)
    if (updatedData.compliment !== undefined) {
        if (cells[4]) {
            cells[4].textContent = truncate(updatedData.compliment, 40);
            cells[4].className = 'compliment-cell has-compliment';
            cells[4].title = updatedData.compliment;
        }
        // Visuelles Feedback
        row.style.transition = 'background-color 0.3s';
        row.style.backgroundColor = 'rgba(245, 158, 11, 0.3)';
        setTimeout(() => {
            row.style.backgroundColor = '';
        }, 1000);
    }
}

function updatePagination(data) {
    document.getElementById('pageInfo').textContent =
        `Seite ${data.page} von ${data.pages || 1}`;
    document.getElementById('prevPage').disabled = data.page <= 1;
    document.getElementById('nextPage').disabled = data.page >= data.pages;
}

function updateCounts(total) {
    // Zeige Total und wie viele auf dieser Seite
    const onPage = state.leads ? state.leads.length : 0;
    document.getElementById('leadCount').textContent = `${total} Leads (${onPage} auf Seite)`;
    document.getElementById('selectedCount').textContent =
        `${state.selectedIds.size} ausgewählt`;
}

function prevPage() {
    if (state.currentPage > 1) {
        state.currentPage--;
        loadLeads();
    }
}

function nextPage() {
    if (state.currentPage < state.totalPages) {
        state.currentPage++;
        loadLeads();
    }
}

function changePerPage() {
    state.perPage = parseInt(document.getElementById('perPageSelect').value);
    state.currentPage = 1;
    loadLeads();
}

// ============================================================
// SELECTION
// ============================================================
function toggleSelection(id, selected) {
    if (selected) {
        state.selectedIds.add(id);
    } else {
        state.selectedIds.delete(id);
    }
    updateCounts(state.leads.length);
}

function toggleAllOnPage() {
    const checked = document.getElementById('selectAllCheckbox').checked;
    state.leads.forEach(lead => {
        if (checked) {
            state.selectedIds.add(lead.id);
        } else {
            state.selectedIds.delete(lead.id);
        }
    });
    loadLeads(); // Re-render to update checkboxes
}

async function selectAll() {
    // ALLE Leads auf ALLEN Seiten auswählen (wie Original)
    const projectId = document.getElementById('projectSelect').value;
    const search = document.getElementById('searchInput').value;
    const filter = state.currentFilter || '';

    try {
        let url = `/api/leads/ids?`;
        if (projectId) url += `project_id=${projectId}&`;
        if (search) url += `search=${encodeURIComponent(search)}&`;
        if (filter) url += `filter=${filter}&`;

        const response = await fetch(url);
        const data = await response.json();

        // Alle IDs hinzufügen
        data.ids.forEach(id => state.selectedIds.add(id));

        showToast(`${state.selectedIds.size} Leads ausgewählt`, 'success');
        updateCounts(state.totalLeads);
        loadLeads();
    } catch (error) {
        console.error('Error selecting all:', error);
        showToast('Fehler beim Auswählen', 'error');
    }
}

function selectPage() {
    // Nur aktuelle Seite auswählen (additiv - andere Seiten bleiben)
    state.leads.forEach(lead => state.selectedIds.add(lead.id));
    showToast(`Seite ausgewählt (${state.selectedIds.size} gesamt)`, 'success');
    updateCounts(state.totalLeads);
    loadLeads();
}

function deselectAll() {
    // ALLE abwählen
    state.selectedIds.clear();
    showToast('Auswahl aufgehoben', 'info');
    updateCounts(0);
    loadLeads();
}

// ============================================================
// SEARCH
// ============================================================
function initSearch() {
    let searchTimeout;
    const searchInput = document.getElementById('searchInput');
    const projectSelect = document.getElementById('projectSelect');

    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            state.currentPage = 1;
            loadLeads();
        }, 300);
    });

    projectSelect.addEventListener('change', () => {
        state.currentPage = 1;
        state.selectedIds.clear();
        loadLeads();
    });
}

// ============================================================
// CSV UPLOAD
// ============================================================
function initUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');

    // Drag & Drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFile(files[0]);
        }
    });

    // File input
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            uploadFile(fileInput.files[0]);
        }
    });
}

async function uploadFile(file) {
    if (!file.name.endsWith('.csv')) {
        showToast('Nur CSV-Dateien erlaubt', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    showProgress('Importiere...', 0);

    try {
        const response = await fetch('/api/import', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            showToast(`✅ ${data.imported} Leads in neues Projekt importiert!`, 'success');
            hideProgress();

            // Lade Projekte neu und wähle das neue Projekt aus
            await loadProjects();

            // Wähle das neu erstellte Projekt aus
            const projectSelect = document.getElementById('projectSelect');
            if (projectSelect && data.project_id) {
                projectSelect.value = data.project_id;
                state.currentProject = data.project_id;
            }

            // Wechsle zur Leads-Ansicht und lade nur Leads des neuen Projekts
            switchView('leads');
            state.currentPage = 1;
            state.selectedIds.clear();
            loadLeads();
        } else {
            showToast(data.error || 'Import fehlgeschlagen', 'error');
            hideProgress();
        }
    } catch (error) {
        showToast('Upload fehlgeschlagen', 'error');
        hideProgress();
        console.error(error);
    }
}

// Projekte laden und Dropdown aktualisieren
async function loadProjects() {
    try {
        const response = await fetch('/api/projects');
        const projects = await response.json();

        const projectSelect = document.getElementById('projectSelect');
        const currentValue = projectSelect.value;

        // Optionen aktualisieren
        projectSelect.innerHTML = '<option value="">Alle Projekte</option>';
        projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project.id;
            option.textContent = `${project.name} (${project.lead_count} Leads)`;
            projectSelect.appendChild(option);
        });

        // Vorherigen Wert wiederherstellen falls vorhanden
        if (currentValue) {
            projectSelect.value = currentValue;
        }
    } catch (error) {
        console.error('Error loading projects:', error);
    }
}

// Projekt löschen
async function deleteProject() {
    const projectSelect = document.getElementById('projectSelect');
    const projectId = projectSelect.value;

    if (!projectId) {
        showToast('Bitte wählen Sie ein Projekt aus', 'warning');
        return;
    }

    const projectName = projectSelect.options[projectSelect.selectedIndex].textContent;

    if (!confirm(`Projekt "${projectName}" wirklich löschen?\n\nAlle Leads in diesem Projekt werden ebenfalls gelöscht!`)) {
        return;
    }

    try {
        const response = await fetch(`/api/projects/${projectId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Projekt gelöscht (${data.deleted_leads} Leads entfernt)`, 'success');
            // Projekte neu laden
            await loadProjects();
            // Auswahl zurücksetzen
            projectSelect.value = '';
            state.selectedIds.clear();
            // Leads neu laden
            loadLeads();
        } else {
            showToast(data.error || 'Fehler beim Löschen', 'error');
        }
    } catch (error) {
        console.error('Error deleting project:', error);
        showToast('Fehler beim Löschen des Projekts', 'error');
    }
}

// ============================================================
// NAME FINDER
// ============================================================
async function findNames() {
    const ids = Array.from(state.selectedIds);
    if (ids.length === 0) {
        showToast('Keine Leads ausgewählt', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/find-names', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_ids: ids })
        });

        const data = await response.json();
        if (data.task_id) {
            state.currentTask = data.task_id;
            pollTaskStatus(data.task_id, 'Namen finden');
        }
    } catch (error) {
        showToast('Fehler beim Starten', 'error');
        console.error(error);
    }
}

// ============================================================
// COMPLIMENT GENERATOR MIT PROMPT-AUSWAHL
// ============================================================
async function generateCompliments() {
    const ids = Array.from(state.selectedIds);
    if (ids.length === 0) {
        showToast('Keine Leads ausgewählt', 'warning');
        return;
    }

    // Speichere IDs für später
    state.complimentLeadIds = ids;

    // Lade Prompts und zeige Modal
    await loadPromptsForSelection();

    document.getElementById('promptSelectInfo').textContent =
        `Wähle einen Prompt für ${ids.length} Lead${ids.length > 1 ? 's' : ''}.`;
    document.getElementById('promptSelectModal').classList.add('active');
}

async function loadPromptsForSelection() {
    try {
        const response = await fetch('/api/prompts');
        const data = await response.json();
        const prompts = data.prompts || [];

        // Speichere Prompts für spätere Referenz
        state.availablePrompts = prompts;

        const list = document.getElementById('promptSelectList');
        list.innerHTML = '';

        prompts.forEach((prompt, idx) => {
            const div = document.createElement('div');
            div.className = 'prompt-option';
            // Markiere Template-Option (ohne KI) visuell
            if (prompt.is_template) {
                div.classList.add('template-option');
            }
            div.onclick = () => selectPromptOption(prompt.id, div);
            div.innerHTML = `
                <input type="radio" name="promptSelect" value="${prompt.id}"
                    data-is-template="${prompt.is_template || false}" id="prompt_${idx}">
                <div class="prompt-option-info">
                    <strong>${escapeHtml(prompt.name)}${prompt.is_template ? ' ⚡' : ''}</strong>
                    <small>${escapeHtml(prompt.description || prompt.prompt?.substring(0, 100) + '...' || '')}</small>
                </div>
            `;
            list.appendChild(div);
        });

        // Ersten Prompt (Template) auswählen falls vorhanden
        if (prompts.length > 0) {
            const firstOption = list.querySelector('.prompt-option');
            if (firstOption) {
                firstOption.classList.add('selected');
                firstOption.querySelector('input').checked = true;
            }
        }
    } catch (error) {
        console.error('Fehler beim Laden der Prompts:', error);
    }
}

function selectPromptOption(promptId, element) {
    // Alle deselektieren
    document.querySelectorAll('#promptSelectList .prompt-option').forEach(el => {
        el.classList.remove('selected');
        el.querySelector('input').checked = false;
    });
    document.getElementById('customPromptRadio').checked = false;
    document.querySelector('.custom-prompt-option').classList.remove('selected');
    document.getElementById('customPromptFields').style.display = 'none';

    // Diese Option selektieren
    element.classList.add('selected');
    element.querySelector('input').checked = true;
}

function selectCustomPrompt() {
    // Alle normalen Prompts deselektieren
    document.querySelectorAll('#promptSelectList .prompt-option').forEach(el => {
        el.classList.remove('selected');
        el.querySelector('input').checked = false;
    });

    // Custom Option selektieren
    document.getElementById('customPromptRadio').checked = true;
    document.querySelector('.custom-prompt-option').classList.add('selected');
    document.getElementById('customPromptFields').style.display = 'block';
}

function closePromptSelectModal() {
    document.getElementById('promptSelectModal').classList.remove('active');
    document.getElementById('customPromptFields').style.display = 'none';
}

async function startComplimentGeneration() {
    const ids = state.complimentLeadIds;
    if (!ids || ids.length === 0) {
        showToast('Keine Leads ausgewählt', 'warning');
        return;
    }

    // Welcher Prompt?
    const customSelected = document.getElementById('customPromptRadio').checked;
    const selectedModel = document.querySelector('input[name="modelSelect"]:checked')?.value || 'deepseek';

    let promptData = {
        lead_ids: ids,
        provider: selectedModel
    };

    if (customSelected) {
        promptData.type = 'custom';
        promptData.system_prompt = document.getElementById('systemPromptText').value;
        promptData.user_prompt = document.getElementById('userPromptText').value;
    } else {
        const selectedRadio = document.querySelector('#promptSelectList input[name="promptSelect"]:checked');
        if (!selectedRadio) {
            showToast('Bitte wähle einen Prompt', 'warning');
            return;
        }
        promptData.type = 'template';
        promptData.prompt_id = selectedRadio.value;

        // Check if this is a template-only prompt (no AI needed!)
        const isTemplate = selectedRadio.dataset.isTemplate === 'true';
        if (isTemplate) {
            promptData.is_template = true;
        }
    }

    closePromptSelectModal();

    try {
        const response = await fetch('/api/generate-compliments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(promptData)
        });

        const data = await response.json();
        if (data.task_id) {
            state.currentTask = data.task_id;
            pollTaskStatus(data.task_id, 'Komplimente generieren');
        } else if (data.error) {
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('Fehler beim Starten', 'error');
        console.error(error);
    }
}

async function deleteCompliments() {
    const ids = Array.from(state.selectedIds);
    if (ids.length === 0) {
        showToast('Keine Leads ausgewählt', 'warning');
        return;
    }

    if (!confirm(`Komplimente von ${ids.length} Leads löschen?`)) {
        return;
    }

    try {
        const response = await fetch('/api/leads/compliments', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_ids: ids })
        });

        const data = await response.json();
        if (data.success) {
            showToast(`${data.deleted} Komplimente gelöscht`, 'success');
            loadLeads();
        } else {
            showToast('Fehler beim Löschen', 'error');
        }
    } catch (error) {
        showToast('Fehler beim Löschen', 'error');
        console.error(error);
    }
}

// ============================================================
// TASK POLLING (mit ETA wie im Original)
// ============================================================
let taskStartTime = null;

function formatTime(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) {
        const m = Math.floor(seconds / 60);
        const s = Math.round(seconds % 60);
        return `${m}m ${s}s`;
    }
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
}

async function pollTaskStatus(taskId, title) {
    taskStartTime = Date.now();
    showProgress(title, 0);

    const poll = async () => {
        try {
            const response = await fetch(`/api/task/${taskId}`);
            const task = await response.json();

            const percent = (task.progress / task.total) * 100;
            const elapsed = (Date.now() - taskStartTime) / 1000;

            // ETA berechnen
            let eta = '--';
            if (task.progress > 0 && task.progress < task.total) {
                const avgTimePerItem = elapsed / task.progress;
                const remaining = (task.total - task.progress) * avgTimePerItem;
                eta = formatTime(remaining);
            }

            // Stats zusammenstellen
            const found = task.found || task.generated || 0;
            const skipped = task.skipped || 0;
            const errors = task.errors || 0;

            updateProgressDetailed(
                title,
                percent,
                `${task.progress} / ${task.total}`,
                `Verstrichene Zeit: ${formatTime(elapsed)} | ETA: ${eta}`,
                found,
                skipped,
                errors,
                task.current || '',
                task.local_found,
                task.web_found
            );

            // ECHTZEIT-UPDATE: Zeile sofort aktualisieren wenn neuer Lead gefunden
            if (task.last_updated) {
                updateTableRow(task.last_updated);
            }

            if (task.status === 'completed') {
                hideProgress();
                const localInfo = task.local_found ? ` (${task.local_found} lokal, ${task.web_found} web)` : '';
                showToast(`${title} abgeschlossen! ${found} gefunden${localInfo}`, 'success');
                loadLeads();

                // Wenn im Einzel-Lead-Modus: Modal-Felder aktualisieren
                if (state.singleLeadMode && state.currentLeadId) {
                    refreshLeadModal(state.currentLeadId);
                    state.singleLeadMode = false;
                }
            } else if (task.status === 'cancelled') {
                hideProgress();
                showToast('Abgebrochen', 'warning');
                loadLeads();
            } else {
                setTimeout(poll, 500); // Schnelleres Polling
            }
        } catch (error) {
            hideProgress();
            console.error(error);
        }
    };

    poll();
}

async function cancelTask() {
    if (state.currentTask) {
        await fetch(`/api/task/${state.currentTask}/cancel`, { method: 'POST' });
    }
}

// ============================================================
// EXPORT
// ============================================================
function exportCSV() {
    const ids = Array.from(state.selectedIds);
    if (ids.length === 0 && !state.currentProject) {
        showToast('Keine Leads ausgewählt', 'warning');
        return;
    }

    let url = '/api/export?';
    if (ids.length > 0) {
        url += `lead_ids=${ids.join(',')}`;
    } else if (state.currentProject) {
        url += `project_id=${state.currentProject}`;
    }

    window.location.href = url;
}

function exportExcel() {
    const ids = Array.from(state.selectedIds);
    if (ids.length === 0 && !state.currentProject) {
        showToast('Keine Leads ausgewählt', 'warning');
        return;
    }

    let url = '/api/export/excel?';
    if (ids.length > 0) {
        url += `lead_ids=${ids.join(',')}`;
    } else if (state.currentProject) {
        url += `project_id=${state.currentProject}`;
    }

    window.location.href = url;
}

// ============================================================
// API CONFIG - Wie im Original!
// ============================================================
let currentActiveProvider = 'deepseek';

async function loadApiConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        currentActiveProvider = config.active_provider || 'deepseek';

        // Update aktiver Provider Badge
        document.getElementById('activeApiName').textContent = currentActiveProvider.toUpperCase();

        // Alle Provider durchgehen
        ['deepseek', 'openai', 'anthropic'].forEach(provider => {
            const isActive = provider === currentActiveProvider;

            // Card styling
            const card = document.getElementById(`apiCard_${provider}`);
            if (card) card.classList.toggle('active', isActive);

            // Active badge
            const badge = document.getElementById(`badge_${provider}`);
            if (badge) badge.classList.toggle('hidden', !isActive);

            // Load values
            if (config.providers && config.providers[provider]) {
                const providerConfig = config.providers[provider];

                const keyInput = document.getElementById(`apiKey_${provider}`);
                if (keyInput && providerConfig.api_key && providerConfig.api_key !== '***hidden***') {
                    keyInput.value = providerConfig.api_key;
                }

                const modelSelect = document.getElementById(`model_${provider}`);
                if (modelSelect && providerConfig.model) {
                    modelSelect.value = providerConfig.model;
                }
            }
        });
    } catch (error) {
        console.error('Error loading API config:', error);
    }
}

async function saveApiConfig() {
    const providers = {};

    ['deepseek', 'openai', 'anthropic'].forEach(provider => {
        const keyInput = document.getElementById(`apiKey_${provider}`);
        const modelSelect = document.getElementById(`model_${provider}`);

        providers[provider] = {
            api_key: keyInput?.value || '',
            model: modelSelect?.value || ''
        };
    });

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                providers,
                active_provider: currentActiveProvider
            })
        });

        if (response.ok) {
            showToast('✅ API-Konfiguration erfolgreich gespeichert!', 'success');
        }
    } catch (error) {
        showToast('Fehler beim Speichern', 'error');
    }
}

function setActiveProvider(provider) {
    currentActiveProvider = provider;

    // UI aktualisieren
    ['deepseek', 'openai', 'anthropic'].forEach(p => {
        const card = document.getElementById(`apiCard_${p}`);
        const badge = document.getElementById(`badge_${p}`);
        const isActive = p === provider;

        if (card) card.classList.toggle('active', isActive);
        if (badge) badge.classList.toggle('hidden', !isActive);
    });

    document.getElementById('activeApiName').textContent = provider.toUpperCase();

    // Speichern
    fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_provider: provider })
    }).then(() => {
        showToast(`✅ ${provider.toUpperCase()} ist jetzt aktiv`, 'success');
    });
}

// ============================================================
// PROMPTS - Wie im Original mit Karten!
// ============================================================
let allPrompts = [];

async function loadPrompts() {
    try {
        const response = await fetch('/api/prompts');
        const data = await response.json();
        allPrompts = data.prompts || [];
        renderPrompts(allPrompts);
    } catch (error) {
        console.error('Error loading prompts:', error);
        document.getElementById('promptsGrid').innerHTML = '<p class="error">Fehler beim Laden der Prompts</p>';
    }
}

function renderPrompts(prompts) {
    const grid = document.getElementById('promptsGrid');
    grid.innerHTML = '';

    if (!prompts || prompts.length === 0) {
        grid.innerHTML = '<p class="empty-message">Keine Prompts vorhanden. Erstelle einen neuen!</p>';
        return;
    }

    prompts.forEach(prompt => {
        const card = document.createElement('div');
        card.className = 'prompt-card';
        // Template-Prompt hat spezielles Styling
        if (prompt.is_template) {
            card.classList.add('template-card');
        }

        const isDefault = prompt.id?.startsWith('standard') || prompt.id?.startsWith('personalisiert')
                        || prompt.id?.startsWith('bewertung') || prompt.id === 'template_no_ai';

        card.innerHTML = `
            <div class="prompt-card-header">
                <h4>${escapeHtml(prompt.name || 'Unbenannt')}${prompt.is_template ? ' ⚡' : ''}</h4>
                <div class="prompt-card-actions">
                    <button class="btn btn-sm btn-primary" onclick="editPrompt('${prompt.id}')">Bearbeiten</button>
                    ${!isDefault ? `<button class="btn btn-sm btn-danger" onclick="deletePrompt('${prompt.id}')">Löschen</button>` : ''}
                </div>
            </div>
            <p class="prompt-description">${escapeHtml(prompt.description || '')}</p>
            <small class="prompt-id">ID: ${escapeHtml(prompt.id || 'N/A')}</small>
        `;
        grid.appendChild(card);
    });
}

function openNewPromptModal() {
    document.getElementById('promptModalTitle').textContent = 'Neuer Prompt erstellen';
    document.getElementById('promptEditId').value = '';
    document.getElementById('promptName').value = '';
    document.getElementById('promptDescription').value = '';
    document.getElementById('promptTargetIndustries').value = '';
    document.getElementById('promptSystemText').value = 'Du bist ein Experte für authentische, personalisierte B2B-Kommunikation.';
    document.getElementById('promptUserText').value = '';
    document.getElementById('promptModal').classList.add('active');
}

function editPrompt(promptId) {
    const prompt = allPrompts.find(p => p.id === promptId);
    if (!prompt) {
        showToast('Prompt nicht gefunden', 'error');
        return;
    }

    document.getElementById('promptModalTitle').textContent = `Prompt bearbeiten - ${prompt.name}`;
    document.getElementById('promptEditId').value = prompt.id || '';
    document.getElementById('promptName').value = prompt.name || '';
    document.getElementById('promptDescription').value = prompt.description || '';
    document.getElementById('promptTargetIndustries').value = (prompt.target_industries || []).join(', ');
    document.getElementById('promptSystemText').value = prompt.system_prompt || '';
    document.getElementById('promptUserText').value = prompt.prompt || prompt.user_prompt_template || '';
    document.getElementById('promptModal').classList.add('active');
}

function closePromptModal() {
    document.getElementById('promptModal').classList.remove('active');
}

async function savePrompt() {
    const editId = document.getElementById('promptEditId').value;
    const name = document.getElementById('promptName').value.trim();
    const userPrompt = document.getElementById('promptUserText').value.trim();

    if (!name || !userPrompt) {
        showToast('Name und User Prompt sind erforderlich', 'warning');
        return;
    }

    const promptData = {
        id: editId || `custom_${Date.now()}`,
        name: name,
        description: document.getElementById('promptDescription').value.trim(),
        target_industries: document.getElementById('promptTargetIndustries').value.split(',').map(s => s.trim()).filter(Boolean),
        system_prompt: document.getElementById('promptSystemText').value.trim(),
        prompt: userPrompt,
        is_template: false
    };

    try {
        const response = await fetch('/api/prompts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(promptData)
        });

        if (response.ok) {
            closePromptModal();
            loadPrompts();
            showToast(`✅ Prompt "${name}" erfolgreich gespeichert!`, 'success');
        } else {
            showToast('Fehler beim Speichern', 'error');
        }
    } catch (error) {
        showToast('Fehler beim Speichern', 'error');
        console.error(error);
    }
}

async function deletePrompt(promptId) {
    if (!confirm(`Möchtest du diesen Prompt wirklich löschen?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/prompts/${promptId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadPrompts();
            showToast('Prompt gelöscht', 'success');
        } else {
            showToast('Fehler beim Löschen', 'error');
        }
    } catch (error) {
        showToast('Fehler beim Löschen', 'error');
    }
}

// ============================================================
// SETTINGS - Backup, Clear DB, Theme
// ============================================================

// Lead-Count beim Laden der Settings-Seite aktualisieren
async function loadSettingsInfo() {
    try {
        const response = await fetch('/api/leads?per_page=1');
        const data = await response.json();
        document.getElementById('totalLeadCount').textContent = data.total || 0;
    } catch (error) {
        document.getElementById('totalLeadCount').textContent = '?';
    }
}

async function createBackup() {
    try {
        showToast('Backup wird erstellt...', 'info');
        const response = await fetch('/api/backup', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showToast(`✅ Backup erfolgreich erstellt:\n${data.filename}`, 'success');
        } else {
            showToast(data.error || 'Backup fehlgeschlagen', 'error');
        }
    } catch (error) {
        showToast('Backup fehlgeschlagen', 'error');
    }
}

function confirmClearDatabase() {
    const count = document.getElementById('totalLeadCount').textContent;

    if (count === '0') {
        showToast('Datenbank ist bereits leer', 'info');
        return;
    }

    const confirmed = confirm(
        `⚠️ WARNUNG - Datenbank leeren\n\n` +
        `Möchtest du wirklich ALLE ${count} Leads löschen?\n` +
        `Diese Aktion kann NICHT rückgängig gemacht werden!\n\n` +
        `Tipp: Erstelle vorher ein Backup!`
    );

    if (confirmed) {
        const doubleConfirmed = confirm(
            `Wirklich löschen?\n\n` +
            `Bist du dir SICHER? Alle ${count} Leads werden permanent gelöscht!`
        );

        if (doubleConfirmed) {
            clearDatabase();
        }
    }
}

async function clearDatabase() {
    try {
        const response = await fetch('/api/leads/clear', { method: 'DELETE' });
        const data = await response.json();

        if (data.success) {
            showToast(`✅ Alle ${data.deleted} Leads wurden erfolgreich gelöscht.`, 'success');
            document.getElementById('totalLeadCount').textContent = '0';
            loadLeads(); // Tabelle aktualisieren
        } else {
            showToast(data.error || 'Fehler beim Löschen', 'error');
        }
    } catch (error) {
        showToast('Fehler beim Löschen der Datenbank', 'error');
    }
}

// ============================================================
// THEME
// ============================================================
function toggleTheme() {
    document.body.classList.toggle('light-mode');
    const isLight = document.body.classList.contains('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    // Sync sidebar toggle
    const darkToggle = document.getElementById('darkModeToggle');
    if (darkToggle) darkToggle.checked = !isLight;
}

function toggleDarkMode() {
    const darkToggle = document.getElementById('darkModeToggle');
    if (darkToggle.checked) {
        // Dark mode aktivieren
        document.body.classList.remove('light-mode');
        localStorage.setItem('theme', 'dark');
    } else {
        // Light mode aktivieren
        document.body.classList.add('light-mode');
        localStorage.setItem('theme', 'light');
    }
}

// Load saved theme on init
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    const darkToggle = document.getElementById('darkModeToggle');

    if (savedTheme === 'light') {
        document.body.classList.add('light-mode');
        if (darkToggle) darkToggle.checked = false;
    } else {
        // Default is dark
        document.body.classList.remove('light-mode');
        if (darkToggle) darkToggle.checked = true;
    }
}

// Init theme on page load
document.addEventListener('DOMContentLoaded', initTheme);

// ============================================================
// PROGRESS (verbessert wie im Original)
// ============================================================
function showProgress(title, percent) {
    const panel = document.getElementById('progressPanel');
    panel.style.display = 'block';
    document.getElementById('progressTitle').textContent = title;
    document.getElementById('progressFill').style.width = `${percent}%`;
    document.getElementById('progressCount').textContent = '0 / 0';
    document.getElementById('progressTime').textContent = 'Verstrichene Zeit: 0s | ETA: --';
    document.getElementById('statOk').textContent = 'OK: 0';
    document.getElementById('statSkip').textContent = 'Skip: 0';
    document.getElementById('statError').textContent = 'Err: 0';
    document.getElementById('progressCurrent').textContent = '';
}

function updateProgressDetailed(title, percent, count, timeInfo, found, skipped, errors, current, localFound, webFound) {
    document.getElementById('progressTitle').textContent = title;
    document.getElementById('progressFill').style.width = `${percent}%`;
    document.getElementById('progressCount').textContent = count;
    document.getElementById('progressTime').textContent = timeInfo;

    // Stats mit Details
    let okText = `OK: ${found}`;
    if (localFound !== undefined && webFound !== undefined) {
        okText = `OK: ${found} (${localFound}L/${webFound}W)`;
    }
    document.getElementById('statOk').textContent = okText;
    document.getElementById('statSkip').textContent = `Skip: ${skipped}`;
    document.getElementById('statError').textContent = `Err: ${errors}`;
    document.getElementById('progressCurrent').textContent = current;
}

function updateProgress(title, percent, info = '', stats = '') {
    document.getElementById('progressTitle').textContent = title;
    document.getElementById('progressFill').style.width = `${percent}%`;
}

function hideProgress() {
    document.getElementById('progressPanel').style.display = 'none';
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

// ============================================================
// UTILS
// ============================================================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================
// FILTER FUNCTIONS (wie im Original Desktop-App!)
// ============================================================

// Erweiterte Filter (Kategorie, Rating, Reviews)
function applyFilters() {
    state.currentPage = 1;
    state.categoryFilter = document.getElementById('categoryFilter')?.value || '';
    state.minRating = document.getElementById('ratingFilter')?.value || '';
    state.minReviews = document.getElementById('reviewsFilter')?.value || '';
    loadLeads();
}

function resetAllFilters() {
    // Alle Filter zurücksetzen
    state.currentFilter = null;
    state.categoryFilter = '';
    state.minRating = '';
    state.minReviews = '';
    state.currentPage = 1;

    // UI zurücksetzen
    const categoryInput = document.getElementById('categoryFilter');
    const ratingSelect = document.getElementById('ratingFilter');
    const reviewsSelect = document.getElementById('reviewsFilter');
    if (categoryInput) categoryInput.value = '';
    if (ratingSelect) ratingSelect.value = '';
    if (reviewsSelect) reviewsSelect.value = '';

    loadLeads();
}

// Quick-Filter Buttons
function filterNoNames() {
    state.currentFilter = 'no_names';
    state.currentPage = 1;
    loadLeads();
}

function filterNoCompliment() {
    state.currentFilter = 'no_compliment';
    state.currentPage = 1;
    loadLeads();
}

function filterComplete() {
    state.currentFilter = 'complete';
    state.currentPage = 1;
    loadLeads();
}

function filterReset() {
    state.currentFilter = null;
    state.currentPage = 1;
    loadLeads();
}

function updateFilterButtons() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    if (state.currentFilter) {
        const filterMap = {
            'no_names': 0,
            'no_compliment': 1,
            'complete': 2
        };
        const idx = filterMap[state.currentFilter];
        if (idx !== undefined) {
            document.querySelectorAll('.filter-btn')[idx]?.classList.add('active');
        }
    } else {
        // "Alle zeigen" aktiv wenn kein Filter
        document.querySelectorAll('.filter-btn')[3]?.classList.add('active');
    }
}

// ============================================================
// LEAD MODAL - ERWEITERT mit allen Feldern!
// ============================================================
async function openLeadModal(leadId) {
    state.currentLeadId = leadId;

    try {
        const response = await fetch(`/api/leads/${leadId}`);
        const lead = await response.json();

        // Titel
        document.getElementById('leadModalTitle').textContent = lead.name || 'Lead Details';

        // Basis-Infos
        document.getElementById('leadName').value = lead.name || '';
        document.getElementById('leadWebsite').value = lead.website || '';
        document.getElementById('leadCategory').value = lead.main_category || '';
        document.getElementById('leadDescription').value = lead.description || '';

        // Kontakt
        document.getElementById('leadEmail').value = lead.email || '';
        document.getElementById('leadPhone').value = lead.phone || '';
        document.getElementById('leadLinkedIn').value = lead.linkedin_url || '';
        document.getElementById('leadLink').value = lead.link || '';

        // Kontaktperson
        document.getElementById('leadFirstName').value = lead.first_name || '';
        document.getElementById('leadLastName').value = lead.last_name || '';
        document.getElementById('leadOwnerName').value = lead.owner_name || '';

        // Adresse
        document.getElementById('leadAddress').value = lead.address || '';
        document.getElementById('leadZipCode').value = lead.zip_code || '';
        document.getElementById('leadCity').value = lead.city || '';
        document.getElementById('leadState').value = lead.state || '';
        document.getElementById('leadCountry').value = lead.country || '';

        // Bewertung
        document.getElementById('leadRating').value = lead.rating ? `⭐ ${lead.rating}` : '';
        document.getElementById('leadReviews').value = lead.review_count || '';
        document.getElementById('leadReviewKeywords').value = lead.review_keywords || '';

        // Kompliment
        document.getElementById('leadCompliment').value = lead.compliment || '';

        document.getElementById('leadModal').classList.add('active');
    } catch (error) {
        showToast('Fehler beim Laden des Leads', 'error');
        console.error(error);
    }
}

function closeLeadModal() {
    document.getElementById('leadModal').classList.remove('active');
    state.currentLeadId = null;
    state.singleLeadMode = false;
}

// Lead-Modal aktualisieren (nach Einzel-Kompliment/Name-Suche)
async function refreshLeadModal(leadId) {
    try {
        const response = await fetch(`/api/leads/${leadId}`);
        const lead = await response.json();

        // Nur die relevanten Felder aktualisieren
        document.getElementById('leadFirstName').value = lead.first_name || '';
        document.getElementById('leadLastName').value = lead.last_name || '';
        document.getElementById('leadCompliment').value = lead.compliment || '';
    } catch (error) {
        console.error('Error refreshing lead modal:', error);
    }
}

async function saveLeadChanges() {
    if (!state.currentLeadId) return;

    // Alle editierbaren Felder sammeln
    const data = {
        name: document.getElementById('leadName').value,
        description: document.getElementById('leadDescription').value,
        main_category: document.getElementById('leadCategory').value,
        email: document.getElementById('leadEmail').value,
        phone: document.getElementById('leadPhone').value,
        linkedin_url: document.getElementById('leadLinkedIn').value,
        first_name: document.getElementById('leadFirstName').value,
        last_name: document.getElementById('leadLastName').value,
        owner_name: document.getElementById('leadOwnerName').value,
        address: document.getElementById('leadAddress').value,
        zip_code: document.getElementById('leadZipCode').value,
        city: document.getElementById('leadCity').value,
        state: document.getElementById('leadState').value,
        country: document.getElementById('leadCountry').value,
        compliment: document.getElementById('leadCompliment').value
    };

    try {
        const response = await fetch(`/api/leads/${state.currentLeadId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showToast('Lead gespeichert', 'success');
            closeLeadModal();
            loadLeads();
        } else {
            showToast('Fehler beim Speichern', 'error');
        }
    } catch (error) {
        showToast('Fehler beim Speichern', 'error');
        console.error(error);
    }
}

async function deleteLeadCompliment() {
    if (!state.currentLeadId) return;

    if (!confirm('Kompliment wirklich löschen?')) return;

    try {
        const response = await fetch(`/api/leads/${state.currentLeadId}/compliment`, {
            method: 'DELETE'
        });

        if (response.ok) {
            document.getElementById('leadCompliment').value = '';
            showToast('Kompliment gelöscht', 'success');
            loadLeads();
        } else {
            showToast('Fehler beim Löschen', 'error');
        }
    } catch (error) {
        showToast('Fehler beim Löschen', 'error');
        console.error(error);
    }
}

// Name für einzelnen Lead suchen
async function findNameForLead() {
    if (!state.currentLeadId) return;

    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Suche...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/find-names', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_ids: [state.currentLeadId] })
        });

        const data = await response.json();

        if (data.task_id) {
            // Auf Ergebnis warten
            let result = null;
            for (let i = 0; i < 60; i++) {
                await new Promise(r => setTimeout(r, 1000));
                const statusResp = await fetch(`/api/task/${data.task_id}`);
                result = await statusResp.json();
                if (result.status === 'completed' || result.status === 'error') break;
            }

            if (result && result.status === 'completed') {
                // Lead-Daten neu laden
                const leadResp = await fetch(`/api/leads/${state.currentLeadId}`);
                const lead = await leadResp.json();
                document.getElementById('leadFirstName').value = lead.first_name || '';
                document.getElementById('leadLastName').value = lead.last_name || '';
                showToast('Name gesucht', 'success');
                loadLeads();
            } else {
                showToast('Kein Name gefunden', 'info');
            }
        }
    } catch (error) {
        showToast('Fehler bei Namenssuche', 'error');
        console.error(error);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Kompliment für einzelnen Lead generieren
async function generateComplimentForLead() {
    if (!state.currentLeadId) return;

    // Lead-ID für Kompliment-Generierung setzen
    state.complimentLeadIds = [state.currentLeadId];
    state.singleLeadMode = true;  // Merken dass wir im Einzel-Modus sind

    // Lade Prompts und zeige Modal
    await loadPromptsForSelection();

    document.getElementById('promptSelectInfo').textContent =
        'Wähle einen Prompt für diesen Lead.';
    document.getElementById('promptSelectModal').classList.add('active');
}
