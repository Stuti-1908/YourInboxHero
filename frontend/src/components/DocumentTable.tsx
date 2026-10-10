import React, { useState, useEffect, useMemo } from 'react';
import { fetchDocumentRequests, deleteDocumentRequest, downloadDocument, updateDocumentStatus, updateDocumentClient } from '../api/invoice';
import type { DocumentRequest } from '../api/invoice';
import './InvoiceTable.css';

interface DocGroup {
  id: string;
  client: DocumentRequest['client'];
  dueDate: string;
  docs: DocumentRequest[];
  openCount: number;
  totalCount: number;
  status: string;
  daysOut: number;
}

export const DocumentTable: React.FC = () => {
  const [docs, setDocs] = useState<DocumentRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');

  const loadDocs = async (silent = false) => {
    try {
      const data = await fetchDocumentRequests();
      setDocs(data);
    } catch (err) {
      console.error(err);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
    const interval = setInterval(() => loadDocs(true), 20000);
    return () => clearInterval(interval);
  }, []);

  const toggleGroup = (id: string) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  const handleDocCheckbox = async (doc: DocumentRequest) => {
    const newStatus = doc.status === 'submitted' ? 'pending' : 'submitted';
    // Optimistic update
    setDocs(prev => prev.map(d => d.id === doc.id ? { ...d, status: newStatus } : d));
    try {
      await updateDocumentStatus(doc.id, newStatus);
    } catch (err) {
      // Revert on error
      setDocs(prev => prev.map(d => d.id === doc.id ? { ...d, status: doc.status } : d));
      console.error(err);
    }
  };

  const handleConsentCheckbox = async (clientId: string, currentConsent: boolean) => {
    const newConsent = !currentConsent;
    // Optimistic update across all docs that share this client
    setDocs(prev => prev.map(d => d.client.id === clientId ? { ...d, client: { ...d.client, voice_call_consent: newConsent } } : d));
    try {
      await updateDocumentClient(clientId, { voice_call_consent: newConsent });
    } catch (err) {
      // Revert on error
      setDocs(prev => prev.map(d => d.client.id === clientId ? { ...d, client: { ...d.client, voice_call_consent: currentConsent } } : d));
      console.error(err);
    }
  };

  const handleDownload = async (doc: DocumentRequest) => {
    try {
      await downloadDocument(doc.id, doc.uploaded_file_name);
    } catch (err: any) {
      alert(err.message || 'Failed to download document');
    }
  };

  const handleDeleteGroup = async (groupDocs: DocumentRequest[]) => {
    if (!confirm(`Are you sure you want to delete these ${groupDocs.length} document request(s)?`)) return;
    try {
      await Promise.all(groupDocs.map(d => deleteDocumentRequest(d.id)));
      setDocs(prev => prev.filter(d => !groupDocs.some(gd => gd.id === d.id)));
    } catch (err) {
      console.error(err);
    }
  };

  const { groups, stats } = useMemo(() => {
    let docsOutstanding = 0;
    let overdue7d = 0;
    let docsReceived = 0;

    const groupMap = new Map<string, DocGroup>();
    const now = new Date();
    // Neutralize time to midnight for accurate day diffs
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const filteredDocs = docs.filter(doc => 
      doc.client.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
      doc.client.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.title.toLowerCase().includes(searchQuery.toLowerCase())
    );

    for (const doc of filteredDocs) {
      // Metrics calc
      if (doc.status === 'submitted' || doc.status === 'approved') {
        docsReceived++;
      } else {
        docsOutstanding++;
        const due = new Date(doc.due_date);
        const dueMidnight = new Date(due.getFullYear(), due.getMonth(), due.getDate());
        const diffTime = today.getTime() - dueMidnight.getTime();
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        if (diffDays >= 7) {
          overdue7d++;
        }
      }

      // Grouping
      const groupId = `${doc.client.id}_${doc.due_date}`;
      if (!groupMap.has(groupId)) {
        const due = new Date(doc.due_date);
        const dueMidnight = new Date(due.getFullYear(), due.getMonth(), due.getDate());
        const diffTime = dueMidnight.getTime() - today.getTime();
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        groupMap.set(groupId, {
          id: groupId,
          client: doc.client,
          dueDate: doc.due_date,
          docs: [],
          openCount: 0,
          totalCount: 0,
          status: 'Pending',
          daysOut: diffDays
        });
      }
      
      const group = groupMap.get(groupId)!;
      group.docs.push(doc);
      group.totalCount++;
      if (doc.status !== 'submitted' && doc.status !== 'approved') {
        group.openCount++;
      }
    }

    const groupsArr = Array.from(groupMap.values());
    for (const group of groupsArr) {
      if (group.openCount === 0 && group.totalCount > 0) {
        group.status = 'Completed';
      } else if (group.daysOut < 0) {
        group.status = 'Overdue';
      }
    }

    // Sort groups: Overdue first, then pending, then completed
    groupsArr.sort((a, b) => {
      if (a.status === 'Completed' && b.status !== 'Completed') return 1;
      if (b.status === 'Completed' && a.status !== 'Completed') return -1;
      return a.daysOut - b.daysOut;
    });

    return { groups: groupsArr, stats: { docsOutstanding, overdue7d, docsReceived } };
  }, [docs, searchQuery]);

  if (loading) return <div className="loading">Loading document requests...</div>;

  return (
    <div className="table-container fade-in">
      <div className="table-header" style={{ marginBottom: '24px' }}>
        <h2>Requests</h2>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', marginBottom: '32px' }}>
        <div style={{ background: '#fff', border: '1px solid var(--color-border)', borderRadius: '8px', padding: '16px 24px', minWidth: '150px' }}>
          <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{stats.docsOutstanding}</div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Documents<br/>outstanding</div>
        </div>
        <div style={{ background: '#fff', border: '1px solid var(--color-border)', borderRadius: '8px', padding: '16px 24px', minWidth: '150px' }}>
          <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{stats.overdue7d}</div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Overdue 7d+</div>
        </div>
        <div style={{ background: '#fff', border: '1px solid var(--color-border)', borderRadius: '8px', padding: '16px 24px', minWidth: '150px' }}>
          <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>{stats.docsReceived}</div>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginTop: '4px' }}>Documents<br/>received</div>
        </div>
      </div>

      <div style={{ background: '#fff', borderRadius: '8px', border: '1px solid var(--color-border)' }}>
        <div style={{ padding: '16px', borderBottom: '1px solid var(--color-border)' }}>
          <input 
            type="text" 
            placeholder="Search by client name or email" 
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="form-input"
            style={{ maxWidth: '400px', margin: 0 }}
          />
        </div>

        <table className="modern-table" style={{ border: 'none', margin: 0 }}>
          <thead>
            <tr>
              <th>CLIENT</th>
              <th>STATUS</th>
              <th>DOCUMENTS</th>
              <th>DAYS OUT</th>
              <th>DEADLINE</th>
              <th style={{ textAlign: 'right' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {groups.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: 'var(--color-text-secondary)' }}>
                  No requests found.
                </td>
              </tr>
            ) : null}
            {groups.map(group => {
              const isExpanded = expandedGroups.has(group.id);
              return (
                <React.Fragment key={group.id}>
                  <tr style={{ background: isExpanded ? '#fafafa' : '#fff' }}>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', display: 'flex', alignItems: 'center' }}>
                        <button 
                          onClick={() => toggleGroup(group.id)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginRight: '8px', fontSize: '0.7rem', color: 'var(--color-text-secondary)' }}
                        >
                          {isExpanded ? '▼' : '▶'}
                        </button>
                        {group.client.name}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginLeft: '18px' }}>{group.client.email}</div>
                    </td>
                    <td>
                      <span style={{ 
                        background: group.status === 'Completed' ? '#dcfce7' : group.status === 'Overdue' ? '#fee2e2' : '#f3f4f6', 
                        color: group.status === 'Completed' ? '#166534' : group.status === 'Overdue' ? '#991b1b' : '#374151',
                        padding: '4px 8px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase'
                      }}>
                        {group.status}
                      </span>
                    </td>
                    <td>
                      {group.totalCount - group.openCount}/{group.totalCount} <span style={{ color: 'var(--color-text-light)' }}>({group.openCount} open)</span>
                    </td>
                    <td style={{ fontWeight: group.daysOut < 0 ? 600 : 400, color: group.daysOut < 0 ? '#dc2626' : 'inherit' }}>
                      {Math.abs(group.daysOut)}
                    </td>
                    <td>{group.dueDate}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn-secondary" onClick={() => toggleGroup(group.id)} style={{ padding: '6px 12px', fontSize: '0.8rem', marginRight: '8px', background: '#fff' }}>
                        {isExpanded ? 'Hide documents' : 'Edit'}
                      </button>
                      <button 
                        onClick={() => handleDeleteGroup(group.docs)} 
                        style={{ background: 'none', border: 'none', color: 'var(--color-text-light)', cursor: 'pointer', fontSize: '1.2rem', padding: '0 8px' }}
                        title="Delete Request"
                      >
                        &times;
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ background: '#fafafa' }}>
                      <td colSpan={6} style={{ padding: '0 20px 20px 35px', borderBottom: '1px solid var(--color-border)' }}>
                        <div style={{ paddingTop: '16px' }}>
                          <p style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', margin: '0 0 16px 0' }}>
                            Tick each document as it arrives. Reminders only ask for what's still outstanding.
                          </p>
                          
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            {group.docs.map(doc => {
                              const isCompleted = doc.status === 'submitted' || doc.status === 'approved';
                              return (
                                <div key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                  <input 
                                    type="checkbox" 
                                    checked={isCompleted} 
                                    onChange={() => handleDocCheckbox(doc)}
                                    style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: 'var(--color-brand-primary)' }}
                                  />
                                  <div style={{ flex: 1, textDecoration: isCompleted ? 'line-through' : 'none', color: isCompleted ? 'var(--color-text-light)' : 'var(--color-text-primary)' }}>
                                    {doc.title}
                                  </div>
                                  {isCompleted && doc.uploaded_file_name && (
                                    <button 
                                      onClick={() => handleDownload(doc)} 
                                      style={{ background: 'none', border: 'none', color: 'var(--color-brand-primary)', cursor: 'pointer', fontSize: '0.85rem' }}
                                    >
                                      Download: {doc.uploaded_file_name}
                                    </button>
                                  )}
                                  <button 
                                    onClick={() => {
                                      navigator.clipboard.writeText(`${window.location.origin}/upload/${doc.upload_token}`);
                                      alert('Upload link copied!');
                                    }}
                                    style={{ background: 'none', border: 'none', color: 'var(--color-text-light)', cursor: 'pointer', fontSize: '0.85rem', textDecoration: 'underline' }}
                                  >
                                    Copy Link
                                  </button>
                                </div>
                              );
                            })}
                          </div>

                          <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px dashed var(--color-border)' }}>
                            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', cursor: 'pointer' }}>
                              <input 
                                type="checkbox" 
                                checked={group.client.voice_call_consent}
                                onChange={() => handleConsentCheckbox(group.client.id, group.client.voice_call_consent)}
                                style={{ width: '16px', height: '16px', marginTop: '2px', accentColor: 'var(--color-brand-primary)' }}
                              />
                              <div>
                                <div style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>Consent form completed</div>
                                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginTop: '2px' }}>
                                  Check the Google Sheet responses, then tick this once confirmed. Required before any SMS or call can go out — until then this client is only ever emailed.
                                </div>
                              </div>
                            </label>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
