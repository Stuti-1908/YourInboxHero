import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { fetchUploadRequestInfo, submitDocumentUpload } from '../api/invoice';
import type { PublicDocumentRequestInfo } from '../api/invoice';
import './Login.css';

const ACCEPTED_EXTENSIONS = '.pdf,.png,.jpg,.jpeg,.doc,.docx';

export const PublicDocumentUpload = () => {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<PublicDocumentRequestInfo | null>(null);
  const [loadError, setLoadError] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [done, setDone] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) return;
    fetchUploadRequestInfo(token)
      .then(setInfo)
      .catch(err => setLoadError(err.message));
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setUploadError('Please choose a file first.');
      return;
    }
    setUploadError('');
    setUploading(true);
    try {
      await submitDocumentUpload(token, file);
      setDone(true);
    } catch (err: any) {
      setUploadError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  if (loadError) {
    return (
      <div className="login-container fade-in">
        <div className="login-card">
          <div className="login-brand">
            <h1>YourInbox<span>Hero</span></h1>
          </div>
          <div className="login-error">{loadError}</div>
          <p style={{ color: 'var(--color-text-light)', marginTop: '12px' }}>
            This link may have expired or already been used. Please contact the business that sent it to you for a new link.
          </p>
        </div>
      </div>
    );
  }

  if (!info) {
    return (
      <div className="login-container fade-in">
        <div className="login-card">
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (done || info.status === 'submitted' || info.status === 'approved') {
    return (
      <div className="login-container fade-in">
        <div className="login-card">
          <div className="login-brand">
            <h1>YourInbox<span>Hero</span></h1>
          </div>
          <h3 style={{ marginTop: 0 }}>Thank you!</h3>
          <p style={{ color: 'var(--color-text-light)' }}>
            {done
              ? `Your document has been received by ${info.business_name}.`
              : `A document (${info.already_uploaded_file_name || 'file'}) has already been submitted for this request.`}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="login-container fade-in">
      <div className="login-card">
        <div className="login-brand">
          <h1>YourInbox<span>Hero</span></h1>
          <p>Document requested by {info.business_name}</p>
        </div>
        <h3 style={{ marginTop: 0 }}>{info.title}</h3>
        {info.description && <p style={{ color: 'var(--color-text-light)' }}>{info.description}</p>}
        <p style={{ color: 'var(--color-text-light)', fontSize: '0.9rem' }}>Due: {info.due_date}</p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-group">
            <label>Choose a file</label>
            <input ref={fileInputRef} type="file" accept={ACCEPTED_EXTENSIONS} required />
            <small style={{ color: 'var(--color-text-light)', fontSize: '0.8rem', marginTop: '4px', display: 'block' }}>
              Accepted: PDF, PNG, JPEG, DOC, DOCX (max 15MB)
            </small>
          </div>
          {uploadError && <div className="login-error">{uploadError}</div>}
          <button type="submit" className="btn-login" disabled={uploading}>
            {uploading ? 'Uploading...' : 'Submit Document'}
          </button>
        </form>
      </div>
    </div>
  );
};
