/**
 * FinDoc AI - Dashboard JavaScript
 * Handles document upload, processing, and dashboard rendering.
 * All data comes from the real backend API — no fake frontend values.
 */

// ============================================================
// Upload Form
// ============================================================

const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const processBtn = document.getElementById('processBtn');
const alertContainer = document.getElementById('alertContainer');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');

// File selection display
fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (file) {
    showFileInfo(file);
  }
});

// Drag and drop
dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('drag-over');
});

dropzone.addEventListener('dragleave', () => {
  dropzone.classList.remove('drag-over');
});

dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) {
    fileInput.files = e.dataTransfer.files;
    showFileInfo(file);
  }
});

function showFileInfo(file) {
  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);
  fileInfo.style.display = 'flex';
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Form submission
uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearAlerts();

  const docType = document.getElementById('documentType').value;
  const file = fileInput.files[0];

  if (!docType) {
    showAlert('error', 'Please select a document type.');
    return;
  }

  if (!file) {
    showAlert('error', 'Please select a file to upload.');
    return;
  }

  // Show loading
  loadingOverlay.classList.add('active');
  loadingText.textContent = `Processing ${file.name}...`;
  processBtn.disabled = true;

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', docType);

    const resp = await fetch('/api/v1/documents/process', {
      method: 'POST',
      body: formData,
    });

    const data = await resp.json();

    if (!resp.ok && resp.status !== 422) {
      // HTTP error
      const errMsg = data.error?.message || data.detail || 'Processing failed.';
      showAlert('error', `Error (${data.error?.code || resp.status}): ${errMsg}`);
    } else if (data.processing_status === 'FAILED' && data.error) {
      // Controlled processing failure
      showAlert('error', `${data.error.code}: ${data.error.message}`);
    } else {
      // Success — navigate to result page
      const name = data.document_name || file.name;
      showAlert('success', `✅ Document processed! Status: ${data.processing_status} | Validation: ${data.validation?.overall_status || 'N/A'}`);

      // Reload document list
      await loadDocuments();

      // Navigate to result after short delay
      setTimeout(() => {
        window.location.href = `/document/${encodeURIComponent(name)}`;
      }, 800);
    }
  } catch (err) {
    showAlert('error', 'Request failed: ' + err.message);
  } finally {
    loadingOverlay.classList.remove('active');
    processBtn.disabled = false;
  }
});

// ============================================================
// Alert Helpers
// ============================================================

function showAlert(type, message) {
  const alert = document.createElement('div');
  alert.className = `alert alert-${type}`;
  alert.innerHTML = `<span>${type === 'error' ? '❌' : '✅'}</span><span>${escHtml(message)}</span>`;
  alertContainer.appendChild(alert);
  setTimeout(() => alert.remove(), 8000);
}

function clearAlerts() {
  alertContainer.innerHTML = '';
}

// ============================================================
// Document List
// ============================================================

async function loadDocuments() {
  try {
    const resp = await fetch('/api/v1/documents');
    if (!resp.ok) throw new Error('Failed to load documents');
    const data = await resp.json();
    renderDocumentList(data.documents || [], data.total || 0);
    updateStats(data.documents || []);
  } catch (err) {
    console.error('Failed to load documents:', err);
  }
}

function renderDocumentList(docs, total) {
  const container = document.getElementById('documentsContainer');

  if (docs.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📂</div>
        <h3>No documents processed yet</h3>
        <p>Upload a document above to get started</p>
      </div>`;
    return;
  }

  let html = `<div class="table-container"><table>
    <thead>
      <tr>
        <th>Document Name</th>
        <th>Type</th>
        <th>Status</th>
        <th>Pages</th>
        <th>OCR</th>
        <th>Processed</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>`;

  docs.forEach(doc => {
    const statusCls = doc.processing_status === 'PASS' ? 'pass' : 'fail';
    const typeLabel = formatDocType(doc.document_type);
    const processedAt = doc.created_at ? new Date(doc.created_at).toLocaleString() : '—';

    html += `
      <tr>
        <td class="primary">${escHtml(doc.document_name)}</td>
        <td><span class="badge badge-info" style="font-size:0.7rem;">${typeLabel}</span></td>
        <td><span class="badge badge-${statusCls}">${doc.processing_status}</span></td>
        <td>${doc.page_count != null ? doc.page_count : '—'}</td>
        <td>${doc.ocr_used ? '<span class="badge badge-warning" style="font-size:0.7rem;">OCR</span>' : '—'}</td>
        <td style="color:var(--text-muted); font-size:0.8rem;">${escHtml(processedAt)}</td>
        <td>
          <a href="/document/${encodeURIComponent(doc.document_name)}" class="btn btn-secondary btn-sm">
            🔍 View
          </a>
        </td>
      </tr>`;
  });

  html += '</tbody></table></div>';
  container.innerHTML = html;
}

function updateStats(docs) {
  const total = docs.length;
  const pass = docs.filter(d => d.processing_status === 'PASS').length;
  const fail = docs.filter(d => d.processing_status === 'FAILED').length;

  document.getElementById('statTotal').textContent = total;
  document.getElementById('statPass').textContent = pass;
  document.getElementById('statFail').textContent = fail;
}

// ============================================================
// Utilities
// ============================================================

function formatDocType(type) {
  const map = {
    invoice: 'Invoice',
    balance_sheet: 'Balance Sheet',
    profit_and_loss: 'Profit & Loss',
    cash_flow_statement: 'Cash Flow',
  };
  return map[type] || type;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ============================================================
// Init
// ============================================================
loadDocuments();
