import React, { useState, useEffect, useRef } from 'react';
import { 
  Briefcase, 
  FileText, 
  UploadCloud, 
  CheckCircle, 
  Play, 
  Terminal, 
  ArrowRight, 
  Search, 
  Sparkles, 
  Trash2, 
  RefreshCw, 
  AlertCircle, 
  User, 
  Mail, 
  FileCheck,
  Lock,
  Globe,
  Settings,
  ShieldCheck
} from 'lucide-react';

const API_BASE = "http://localhost:8000/api";

function App() {
  const [activeTab, setActiveTab] = useState("upload");
  const [resumes, setResumes] = useState([]);
  const [activeResumeId, setActiveResumeId] = useState(null);
  const [activeResume, setActiveResume] = useState(null);
  
  // Scraper & Jobs states
  const [jobs, setJobs] = useState([]);
  const [scrapingQuery, setScrapingQuery] = useState("Stripe");
  const [scrapingLocation, setScrapingLocation] = useState("");
  const [scrapingPlatform, setScrapingPlatform] = useState(""); // "", "linkedin", "naukri"
  const [isScraping, setIsScraping] = useState(false);
  const [isMatching, setIsMatching] = useState(false);

  // Credentials states
  const [credentials, setCredentials] = useState([]);
  const [newCred, setNewCred] = useState({
    platform: "linkedin",
    username: "",
    password: ""
  });
  const [isSavingCred, setIsSavingCred] = useState(false);

  // Matching & Application states
  const [matches, setMatches] = useState([]);
  const [selectedAppId, setSelectedAppId] = useState(null);
  const [appDetail, setAppDetail] = useState(null);
  const [isTailoring, setIsTailoring] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  // User input states for Playwright applying
  const [applicantInfo, setApplicantInfo] = useState({
    firstName: "John",
    lastName: "Doe",
    email: "johndoe@example.com"
  });

  // Health check
  const [healthStatus, setHealthStatus] = useState("connecting");

  // Terminal scroll reference
  const terminalEndRef = useRef(null);

  useEffect(() => {
    fetchResumes();
    fetchJobs();
    fetchCredentials();
    checkHealth();
  }, []);

  // Poll application logs if actively applying
  useEffect(() => {
    let intervalId;
    if (selectedAppId && appDetail && (appDetail.status === "applying" || isApplying)) {
      intervalId = setInterval(() => {
        fetchApplicationDetail(selectedAppId, false); // Fetch silently
      }, 2000);
    }
    return () => clearInterval(intervalId);
  }, [selectedAppId, appDetail, isApplying]);

  // Scroll terminal logs to bottom
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [appDetail?.logs]);

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        setHealthStatus("online");
      } else {
        setHealthStatus("offline");
      }
    } catch {
      setHealthStatus("offline");
    }
  };

  const fetchResumes = async () => {
    try {
      const res = await fetch(`${API_BASE}/resumes`);
      if (res.ok) {
        const data = await res.json();
        setResumes(data);
        if (data.length > 0 && !activeResumeId) {
          setActiveResumeId(data[0].id);
          fetchResumeDetail(data[0].id);
        }
      }
    } catch (e) {
      console.error("Error fetching resumes:", e);
    }
  };

  const fetchResumeDetail = async (id) => {
    try {
      const res = await fetch(`${API_BASE}/resumes/${id}`);
      if (res.ok) {
        const data = await res.json();
        setActiveResume(data);
      }
    } catch (e) {
      console.error("Error fetching resume details:", e);
    }
  };

  const fetchJobs = async () => {
    try {
      const res = await fetch(`${API_BASE}/jobs`);
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
      }
    } catch (e) {
      console.error("Error fetching jobs:", e);
    }
  };

  const fetchCredentials = async () => {
    try {
      const res = await fetch(`${API_BASE}/credentials`);
      if (res.ok) {
        const data = await res.json();
        setCredentials(data);
      }
    } catch (e) {
      console.error("Error fetching credentials:", e);
    }
  };

  const handleDeleteResume = async (id, e) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this resume?")) return;
    try {
      const res = await fetch(`${API_BASE}/resumes/${id}`, { method: "DELETE" });
      if (res.ok) {
        setResumes(resumes.filter(r => r.id !== id));
        if (activeResumeId === id) {
          setActiveResumeId(null);
          setActiveResume(null);
        }
      }
    } catch (e) {
      console.error("Error deleting resume:", e);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      setHealthStatus("processing");
      const res = await fetch(`${API_BASE}/resumes/upload`, {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        setResumes([data, ...resumes]);
        setActiveResumeId(data.id);
        setActiveResume(data);
        alert("Resume successfully uploaded, parsed, and indexed!");
      } else {
        const err = await res.json();
        alert(`Parsing failed: ${err.detail || "Server error"}`);
      }
    } catch (err) {
      alert(`Upload error: ${err.message}`);
    } finally {
      checkHealth();
    }
  };

  // Credentials management
  const handleSaveCredentials = async (e) => {
    e.preventDefault();
    if (!newCred.username || !newCred.password) {
      alert("Please fill in both username and password fields.");
      return;
    }
    setIsSavingCred(true);
    try {
      const res = await fetch(`${API_BASE}/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newCred)
      });
      if (res.ok) {
        alert("Credentials saved securely.");
        setNewCred({ ...newCred, username: "", password: "" });
        fetchCredentials();
      } else {
        alert("Failed to save credentials.");
      }
    } catch (err) {
      alert(`Error saving: ${err.message}`);
    } finally {
      setIsSavingCred(false);
    }
  };

  const handleTestCredentials = async (platform) => {
    alert("Test process started. A headful browser will open briefly on the server to verify credentials and cache session cookies. Please enter OTP or bypass CAPTCHA in the open browser if prompted.");
    try {
      const res = await fetch(`${API_BASE}/credentials/${platform}/test`, { method: "POST" });
      if (res.ok) {
        alert("Login verification check triggered in background. Monitor the browser window or refresh saved accounts statuses in a moment.");
        // Poll credential state in 5s
        setTimeout(fetchCredentials, 8000);
      }
    } catch (err) {
      alert(`Test trigger error: ${err.message}`);
    }
  };

  const handleDeleteCredentials = async (platform) => {
    if (!confirm(`Are you sure you want to disconnect and delete your ${platform} credentials?`)) return;
    try {
      const res = await fetch(`${API_BASE}/credentials/${platform}`, { method: "DELETE" });
      if (res.ok) {
        fetchCredentials();
      }
    } catch (err) {
      alert(`Delete error: ${err.message}`);
    }
  };

  // Trigger scraper
  const handleScrapeJobs = async () => {
    if (!scrapingQuery) return;
    setIsScraping(true);
    try {
      let url = `${API_BASE}/jobs/scrape?query=${encodeURIComponent(scrapingQuery)}&location=${encodeURIComponent(scrapingLocation)}`;
      if (scrapingPlatform) {
        url += `&platform=${scrapingPlatform}`;
      }
      const res = await fetch(url, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        fetchJobs();
        alert(data.message || "Scraping completed!");
      } else {
        const err = await res.json();
        alert(`Scraping failed: ${err.detail || "Server error"}`);
      }
    } catch (e) {
      alert(`Scraping failed: ${e.message}`);
    } finally {
      setIsScraping(false);
    }
  };

  // Run matching flow
  const handleMatchResume = async () => {
    if (!activeResumeId) {
      alert("Please upload and select a resume first.");
      return;
    }
    setIsMatching(true);
    try {
      const res = await fetch(`${API_BASE}/matching/match?resume_id=${activeResumeId}`);
      if (res.ok) {
        const data = await res.json();
        setMatches(data.matches);
        setActiveTab("matching");
      }
    } catch (e) {
      alert(`Matching failed: ${e.message}`);
    } finally {
      setIsMatching(false);
    }
  };

  const fetchApplicationDetail = async (appId, resetLoading = true) => {
    try {
      const res = await fetch(`${API_BASE}/applications/${appId}`);
      if (res.ok) {
        const data = await res.json();
        setAppDetail(data);
        if (data.status === "applied" || data.status === "failed") {
          setIsApplying(false);
        }
      }
    } catch (e) {
      console.error("Error fetching app details:", e);
    }
  };

  const handleSelectApplication = (appId) => {
    setSelectedAppId(appId);
    fetchApplicationDetail(appId);
    setActiveTab("applications");
  };

  // Tailor Resume
  const handleTailorResume = async (appId) => {
    setIsTailoring(true);
    try {
      const res = await fetch(`${API_BASE}/applications/${appId}/tailor`, {
        method: "POST"
      });
      if (res.ok) {
        await fetchApplicationDetail(appId);
        alert("Resume successfully tailored and graded by ATS Critic!");
      }
    } catch (e) {
      alert(`Tailoring failed: ${e.message}`);
    } finally {
      setIsTailoring(false);
    }
  };

  // Approve Tailoring
  const handleApproveTailoring = async (appId) => {
    try {
      const res = await fetch(`${API_BASE}/applications/${appId}/approve`, {
        method: "POST"
      });
      if (res.ok) {
        await fetchApplicationDetail(appId);
        alert("Tailoring approved! Ready to apply.");
      }
    } catch (e) {
      alert(`Approval failed: ${e.message}`);
    }
  };

  // Trigger Playwright Automation
  const handleApplyAutomation = async (appId) => {
    setIsApplying(true);
    try {
      const res = await fetch(`${API_BASE}/applications/${appId}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: applicantInfo.firstName,
          last_name: applicantInfo.lastName,
          email: applicantInfo.email,
          headful: true
        })
      });
      if (res.ok) {
        fetchApplicationDetail(appId);
      } else {
        setIsApplying(false);
        alert("Failed to start application automation.");
      }
    } catch (e) {
      setIsApplying(false);
      alert(`Apply error: ${e.message}`);
    }
  };

  const handleClearDatabase = async () => {
    if (!confirm("Are you sure you want to delete all resumes, crawled jobs, application logs, and clear the vector indexes? This action cannot be undone.")) return;
    try {
      setHealthStatus("processing");
      const res = await fetch(`${API_BASE}/jobs/clear`, { method: "POST" });
      if (res.ok) {
        setResumes([]);
        setActiveResumeId(null);
        setActiveResume(null);
        setJobs([]);
        setMatches([]);
        setSelectedAppId(null);
        setAppDetail(null);
        setActiveTab("upload");
        alert("All database records and vector indexes cleared successfully!");
      } else {
        alert("Failed to clear database.");
      }
    } catch (e) {
      alert(`Error clearing database: ${e.message}`);
    } finally {
      checkHealth();
    }
  };

  return (
    <div className="app-container">
      {/* Header Banner */}
      <header>
        <div className="logo-section">
          <div className="logo-icon">AG</div>
          <div className="logo-text">
            <h1>AutoJob Agent</h1>
            <p>Open Source Resume Tailoring & Browser Application Agent</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button 
            className="btn" 
            onClick={handleClearDatabase} 
            style={{ 
              background: 'rgba(239, 68, 68, 0.1)', 
              color: '#f87171', 
              borderColor: 'rgba(239, 68, 68, 0.3)',
              padding: '0.4rem 0.85rem',
              fontSize: '0.8rem'
            }}
          >
            <Trash2 size={14} />
            Clear Database
          </button>
          <span className={`status-badge ${
            healthStatus === 'online' ? 'status-approved' : 
            healthStatus === 'processing' ? 'status-applying' : 'status-failed'
          }`}>
            Backend: {healthStatus}
          </span>
          {healthStatus === 'offline' && (
            <button className="btn" onClick={checkHealth} style={{ padding: '0.25rem 0.5rem' }}>
              <RefreshCw size={14} />
            </button>
          )}
        </div>
      </header>

      {/* Primary Tab Navigation */}
      <div className="tabs">
        <button 
          className={`tab-btn ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab("upload")}
        >
          <FileText size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          1. Resume & Accounts
        </button>
        <button 
          className={`tab-btn ${activeTab === 'matching' ? 'active' : ''}`}
          onClick={() => setActiveTab("matching")}
          disabled={!activeResumeId}
        >
          <Briefcase size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          2. Match Rankings ({matches.length})
        </button>
        <button 
          className={`tab-btn ${activeTab === 'applications' ? 'active' : ''}`}
          onClick={() => setActiveTab("applications")}
          disabled={!selectedAppId}
        >
          <Sparkles size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          3. Tailoring & Apply
        </button>
      </div>

      {/* Tab 1: Upload & Accounts Connection */}
      {activeTab === "upload" && (
        <div className="dashboard-grid">
          {/* Left Column: CV uploads & Saved Credentials */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            
            {/* Resume Upload Box */}
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>Resume Portal</h2>
              
              <div className="upload-zone" onClick={() => document.getElementById('pdf-file-input').click()}>
                <UploadCloud className="upload-icon" />
                <p style={{ fontWeight: 600, fontSize: '0.95rem' }}>Upload CV (PDF format)</p>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.25rem' }}>BGE-M3 local indexing on upload</p>
                <input 
                  id="pdf-file-input"
                  type="file" 
                  accept="application/pdf"
                  onChange={handleFileUpload} 
                  style={{ display: 'none' }} 
                />
              </div>

              {/* CV List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Your Uploaded CVs:</h3>
                {resumes.map(r => (
                  <div 
                    key={r.id} 
                    onClick={() => { setActiveResumeId(r.id); fetchResumeDetail(r.id); }}
                    className="glass-card" 
                    style={{ 
                      cursor: 'pointer',
                      borderColor: activeResumeId === r.id ? 'var(--primary)' : 'var(--border-color)',
                      background: activeResumeId === r.id ? 'var(--primary-glow)' : 'rgba(15, 19, 26, 0.65)',
                      padding: '1rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <FileCheck size={20} color={activeResumeId === r.id ? '#818cf8' : '#64748b'} />
                      <span style={{ fontSize: '0.9rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '180px', whiteSpace: 'nowrap' }}>
                        {r.filename}
                      </span>
                    </div>
                    <button 
                      type="button"
                      className="btn" 
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleDeleteResume(r.id, e);
                      }} 
                      style={{ padding: '0.35rem', border: 'none', background: 'transparent', cursor: 'pointer' }}
                    >
                      <Trash2 size={16} color="#ef4444" />
                    </button>
                  </div>
                ))}
              </div>

              {activeResume && (
                <div className="glass-card" style={{ marginTop: '0.5rem', padding: '1rem' }}>
                  <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '0.5rem' }}>Parsed CV Profile</h3>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    <strong>Experience:</strong> {activeResume.parsed_experience} years
                  </p>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                    <strong>Location:</strong> {activeResume.parsed_location}
                  </p>
                  <div style={{ marginTop: '0.75rem' }}>
                    <strong style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Parsed Skills:</strong>
                    <div className="tag-container">
                      {(activeResume.parsed_skills || []).map((skill, idx) => (
                        <span key={idx} className="tag tag-primary">{skill}</span>
                      ))}
                    </div>
                  </div>

                  {(activeResume.linkedin_url || activeResume.github_url || activeResume.portfolio_url) && (
                    <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
                      <strong style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Contact & Portfolios:</strong>
                      {activeResume.linkedin_url && (
                        <p style={{ fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <span style={{ color: 'var(--text-muted)' }}>LinkedIn: </span>
                          <a href={activeResume.linkedin_url.startsWith("http") ? activeResume.linkedin_url : `https://${activeResume.linkedin_url}`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--secondary)', textDecoration: 'none' }}>
                            {activeResume.linkedin_url}
                          </a>
                        </p>
                      )}
                      {activeResume.github_url && (
                        <p style={{ fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <span style={{ color: 'var(--text-muted)' }}>GitHub: </span>
                          <a href={activeResume.github_url.startsWith("http") ? activeResume.github_url : `https://${activeResume.github_url}`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--secondary)', textDecoration: 'none' }}>
                            {activeResume.github_url}
                          </a>
                        </p>
                      )}
                      {activeResume.portfolio_url && (
                        <p style={{ fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <span style={{ color: 'var(--text-muted)' }}>Portfolio: </span>
                          <a href={activeResume.portfolio_url.startsWith("http") ? activeResume.portfolio_url : `https://${activeResume.portfolio_url}`} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--secondary)', textDecoration: 'none' }}>
                            {activeResume.portfolio_url}
                          </a>
                        </p>
                      )}
                    </div>
                  )}
                  
                  <button 
                    className="btn btn-primary" 
                    onClick={handleMatchResume} 
                    disabled={isMatching}
                    style={{ width: '100%', marginTop: '1.25rem' }}
                  >
                    {isMatching ? 'Searching Qdrant...' : 'Compute Match Rankings'}
                    <ArrowRight size={16} />
                  </button>
                </div>
              )}
            </div>

            {/* Connected Accounts Manager */}
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>Connect Job Accounts</h2>
              
              <form onSubmit={handleSaveCredentials} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button 
                    type="button"
                    className={`btn ${newCred.platform === 'linkedin' ? 'btn-primary' : ''}`}
                    onClick={() => setNewCred({ ...newCred, platform: "linkedin" })}
                    style={{ flex: 1, padding: '0.4rem' }}
                  >
                    LinkedIn
                  </button>
                  <button 
                    type="button"
                    className={`btn ${newCred.platform === 'naukri' ? 'btn-primary' : ''}`}
                    onClick={() => setNewCred({ ...newCred, platform: "naukri" })}
                    style={{ flex: 1, padding: '0.4rem' }}
                  >
                    Naukri
                  </button>
                </div>

                <div className="input-group">
                  <span className="input-label">Username / Email</span>
                  <div style={{ position: 'relative' }}>
                    <User size={14} style={{ position: 'absolute', left: '10px', top: '11px', color: 'var(--text-muted)' }} />
                    <input 
                      type="text" 
                      value={newCred.username}
                      onChange={(e) => setNewCred({ ...newCred, username: e.target.value })}
                      placeholder="email@example.com"
                      className="input-field" 
                      style={{ paddingLeft: '2.25rem' }}
                    />
                  </div>
                </div>

                <div className="input-group">
                  <span className="input-label">Password</span>
                  <div style={{ position: 'relative' }}>
                    <Lock size={14} style={{ position: 'absolute', left: '10px', top: '11px', color: 'var(--text-muted)' }} />
                    <input 
                      type="password" 
                      value={newCred.password}
                      onChange={(e) => setNewCred({ ...newCred, password: e.target.value })}
                      placeholder="••••••••"
                      className="input-field" 
                      style={{ paddingLeft: '2.25rem' }}
                    />
                  </div>
                </div>

                <button type="submit" className="btn btn-primary" disabled={isSavingCred} style={{ width: '100%' }}>
                  <ShieldCheck size={16} />
                  Securely Save Account
                </button>
              </form>

              {/* Saved accounts list */}
              <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Saved Job Portals:</h3>
                {credentials.map(c => (
                  <div key={c.id} className="glass-card" style={{ padding: '0.85rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h4 style={{ fontSize: '0.9rem', fontWeight: 700, textTransform: 'capitalize' }}>{c.platform}</h4>
                      <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{c.username}</p>
                      <div style={{ marginTop: '0.25rem' }}>
                        <span className={`status-badge ${c.has_session ? 'status-approved' : 'status-failed'}`} style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem' }}>
                          {c.has_session ? 'Authenticated Session' : 'Needs Verification'}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                      <button 
                        type="button"
                        className="btn" 
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          handleTestCredentials(c.platform);
                        }} 
                        style={{ padding: '0.35rem 0.6rem', fontSize: '0.75rem', cursor: 'pointer' }}
                      >
                        Test Login
                      </button>
                      <button 
                        type="button"
                        className="btn" 
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          handleDeleteCredentials(c.platform);
                        }} 
                        style={{ padding: '0.35rem', border: 'none', background: 'transparent', cursor: 'pointer' }}
                      >
                        <Trash2 size={14} color="#ef4444" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Scraper & Crawl List */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div>
              <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>Job Discovery Crawler</h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Find jobs by querying Greenhouse/Lever APIs or using connected accounts to crawl LinkedIn/Naukri.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <div className="input-group" style={{ flex: 1.5, minWidth: '180px' }}>
                <span className="input-label">Search Keyword / Company</span>
                <input 
                  type="text" 
                  value={scrapingQuery}
                  onChange={(e) => setScrapingQuery(e.target.value)}
                  placeholder="e.g. Stripe, FastAPI Developer"
                  className="input-field" 
                />
              </div>
              <div className="input-group" style={{ flex: 1, minWidth: '120px' }}>
                <span className="input-label">Location (Optional)</span>
                <input 
                  type="text" 
                  value={scrapingLocation}
                  onChange={(e) => setScrapingLocation(e.target.value)}
                  placeholder="e.g. Remote, Bengaluru"
                  className="input-field" 
                />
              </div>
              <div className="input-group" style={{ flex: 1, minWidth: '150px' }}>
                <span className="input-label">Source Board</span>
                <select 
                  className="input-field" 
                  value={scrapingPlatform} 
                  onChange={(e) => setScrapingPlatform(e.target.value)}
                  style={{ background: '#0f131a', color: 'var(--text-primary)' }}
                >
                  <option value="">Greenhouse / Lever API</option>
                  <option value="linkedin">LinkedIn Crawler</option>
                  <option value="naukri">Naukri Crawler</option>
                </select>
              </div>
            </div>

            <button className="btn btn-primary" onClick={handleScrapeJobs} disabled={isScraping} style={{ alignSelf: 'flex-start' }}>
              <Search size={16} />
              {isScraping ? 'Discovering Jobs...' : 'Trigger Crawler Scrape'}
            </button>

            {/* List of Crawled Jobs */}
            <div style={{ marginTop: '1rem' }}>
              <h3 style={{ fontSize: '0.95rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                Indexed Database Opportunities ({jobs.length})
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxHeight: '480px', overflowY: 'auto', paddingRight: '0.25rem' }}>
                {jobs.map(job => (
                  <div key={job.id} className="glass-card" style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 700 }}>{job.title}</h4>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{job.company} • {job.location}</p>
                      </div>
                      <a href={job.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.75rem', color: 'var(--secondary)', textDecoration: 'none' }}>
                        View Post
                      </a>
                    </div>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.5rem', lineBreak: 'anywhere' }}>
                      {job.description.length > 200 ? `${job.description.substring(0, 200)}...` : job.description}
                    </p>
                    <div className="tag-container" style={{ marginTop: '0.75rem' }}>
                      {(job.skills_required || []).map((s, idx) => (
                        <span key={idx} className="tag">{s}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Match Rankings */}
      {activeTab === "matching" && (
        <div className="glass-panel">
          <h2 className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '0.5rem' }}>
            Hybrid Semantic & Keyword Match Rankings
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
            Calculated via Qdrant dense vector cosine distance + lexical skill tags intersections, refined by BGE-Reranker-Large.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {matches.map((m, idx) => (
              <div key={idx} className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.25rem' }}>
                <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                  <div className="score-badge">
                    {m.match_percentage}%
                    <span style={{ display: 'block', fontSize: '0.6rem', color: 'var(--text-muted)', fontWeight: 500 }}>score</span>
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>{m.title}</h3>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{m.company} • {m.location}</p>
                    <div style={{ marginTop: '0.5rem' }}>
                      <span className={`status-badge status-${m.status}`}>
                        {m.status}
                      </span>
                    </div>
                  </div>
                </div>

                <button className="btn btn-primary" onClick={() => handleSelectApplication(m.application_id)}>
                  Review & Tailor CV
                  <ArrowRight size={16} />
                </button>
              </div>
            ))}

            {matches.length === 0 && (
              <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                <AlertCircle size={48} style={{ margin: '0 auto 1rem', display: 'block' }} />
                <p>No matches generated yet. Make sure your active resume and crawler databases are populated.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Tailoring & Apply */}
      {activeTab === "applications" && appDetail && (
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Top Summary Banner */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span className={`status-badge status-${appDetail.status}`}>
                  Status: {appDetail.status}
                </span>
                <span className="tag" style={{ background: '#1e293b', border: 'none', color: '#cbd5e1' }}>
                  ATS: {appDetail.ats_type}
                </span>
              </div>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 800 }}>{appDetail.job_title}</h2>
              <p style={{ color: 'var(--text-secondary)' }}>{appDetail.job_company} • Recommendation Match: {appDetail.match_score}%</p>
            </div>
            
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button 
                className="btn" 
                onClick={() => handleTailorResume(appDetail.id)} 
                disabled={isTailoring}
              >
                <Sparkles size={16} />
                {isTailoring ? 'Rewriting & Critic loops...' : 'Regenerate Tailoring'}
              </button>
              {appDetail.status === 'tailored' && (
                <button className="btn btn-primary" onClick={() => handleApproveTailoring(appDetail.id)}>
                  Approve Version
                </button>
              )}
            </div>
          </div>

          {/* Step 5: ATS Critic Rating details */}
          {appDetail.ats_score !== null && (
            <div className="glass-card" style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', borderLeft: '4px solid var(--secondary)', background: 'rgba(6, 182, 212, 0.02)' }}>
              <div style={{ flex: '0 0 100px', textAlign: 'center' }}>
                <div style={{ 
                  fontSize: '2rem', 
                  fontWeight: 800, 
                  color: appDetail.ats_score >= 75 ? 'var(--success)' : 'var(--warning)',
                  background: 'rgba(255,255,255,0.03)',
                  padding: '1rem 0.5rem',
                  borderRadius: '12px',
                  border: '1px solid var(--border-color)'
                }}>
                  {appDetail.ats_score}%
                </div>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.25rem', fontWeight: 600 }}>
                  ATS Critic Rating
                </span>
              </div>
              <div style={{ flex: 1, minWidth: '250px' }}>
                <h3 style={{ fontSize: '0.95rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <ShieldCheck size={16} color="#06b6d4" />
                  Critic Feedback & Correction Loops
                </h3>
                {appDetail.ats_critic_feedback && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      <strong>Loops Run:</strong> {appDetail.ats_critic_feedback.attempts_run || 1} of 3 (Auto re-tailored to exceed 75% threshold)
                    </p>
                    <div style={{ marginTop: '0.5rem' }}>
                      <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Missing Keywords Flagged:</strong>
                      <div className="tag-container" style={{ marginTop: '0.25rem' }}>
                        {(appDetail.ats_critic_feedback.missing_keywords || []).length > 0 ? (
                          (appDetail.ats_critic_feedback.missing_keywords).map((kw, idx) => (
                            <span key={idx} className="tag" style={{ color: '#ef4444', background: 'rgba(239, 68, 68, 0.05)', borderColor: 'rgba(239, 68, 68, 0.2)' }}>
                              {kw}
                            </span>
                          ))
                        ) : (
                          <span style={{ fontSize: '0.75rem', color: 'var(--success)' }}>None! CV keywords perfectly aligned.</span>
                        )}
                      </div>
                    </div>
                    <div style={{ marginTop: '0.75rem' }}>
                      <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Improvement Bullet Points:</strong>
                      <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        {(appDetail.ats_critic_feedback.recommendations || []).map((rec, idx) => (
                          <li key={idx} style={{ marginBottom: '0.25rem' }}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Left/Right Text Diff Panel */}
          <div className="tailoring-container">
            {/* Original Resume Text */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>Original Resume Content</h3>
              <div className="text-area-view">{appDetail.resume_raw}</div>
            </div>

            {/* Tailored Output */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--accent)' }}>Tailored Resume Version</h3>
              {appDetail.tailored_content ? (
                <div className="text-area-view" style={{ borderColor: 'var(--accent)' }}>
                  {appDetail.tailored_content}
                </div>
              ) : (
                <div className="text-area-view" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--text-muted)' }}>
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ marginBottom: '1rem' }}>No tailored CV version generated yet.</p>
                    <button className="btn btn-primary" onClick={() => handleTailorResume(appDetail.id)} disabled={isTailoring}>
                      <Sparkles size={16} />
                      {isTailoring ? 'Running Agent Rewrite...' : 'Generate Tailored Resume'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Cover Letter Section */}
          {appDetail.cover_letter && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>Custom Cover Letter</h3>
              <div className="text-area-view" style={{ minHeight: '160px' }}>{appDetail.cover_letter}</div>
            </div>
          )}

          {/* Playwright Application Gateway */}
          <div className="glass-card" style={{ borderLeft: '4px solid var(--primary)', display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '0.5rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 800 }}>Playwright Application Gateway</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Provide the details you want the Playwright browser automation agent to fill in. When triggered, Playwright opens a browser session, inputs these fields, uploads your tailored resume file, writes the cover letter, and pauses so you can verify before submitting.
            </p>

            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <div className="input-group" style={{ flex: 1, minWidth: '200px' }}>
                <span className="input-label">First Name</span>
                <div style={{ position: 'relative' }}>
                  <User size={16} style={{ position: 'absolute', left: '10px', top: '12px', color: 'var(--text-muted)' }} />
                  <input 
                    type="text" 
                    value={applicantInfo.firstName}
                    onChange={(e) => setApplicantInfo({ ...applicantInfo, firstName: e.target.value })}
                    className="input-field" 
                    style={{ paddingLeft: '2.25rem' }}
                  />
                </div>
              </div>
              <div className="input-group" style={{ flex: 1, minWidth: '200px' }}>
                <span className="input-label">Last Name</span>
                <div style={{ position: 'relative' }}>
                  <User size={16} style={{ position: 'absolute', left: '10px', top: '12px', color: 'var(--text-muted)' }} />
                  <input 
                    type="text" 
                    value={applicantInfo.lastName}
                    onChange={(e) => setApplicantInfo({ ...applicantInfo, lastName: e.target.value })}
                    className="input-field" 
                    style={{ paddingLeft: '2.25rem' }}
                  />
                </div>
              </div>
              <div className="input-group" style={{ flex: 2, minWidth: '250px' }}>
                <span className="input-label">Email Address</span>
                <div style={{ position: 'relative' }}>
                  <Mail size={16} style={{ position: 'absolute', left: '10px', top: '12px', color: 'var(--text-muted)' }} />
                  <input 
                    type="text" 
                    value={applicantInfo.email}
                    onChange={(e) => setApplicantInfo({ ...applicantInfo, email: e.target.value })}
                    className="input-field" 
                    style={{ paddingLeft: '2.25rem' }}
                  />
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginTop: '0.5rem' }}>
              <button 
                className="btn btn-primary" 
                onClick={() => handleApplyAutomation(appDetail.id)} 
                disabled={isApplying}
                style={{ padding: '0.85rem 2rem' }}
              >
                <Play size={16} />
                {isApplying ? 'Applying in background...' : 'Launch Playwright Auto-Apply'}
              </button>
            </div>

            {/* Real-time console logs */}
            {(appDetail.logs || isApplying) && (
              <div style={{ marginTop: '0.5rem' }}>
                <h4 style={{ fontSize: '0.85rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)' }}>
                  <Terminal size={14} />
                  Live Browser Automation Console Logs ({appDetail.ats_type} Flow)
                </h4>
                <div className="terminal-console">
                  {(appDetail.logs || "").split("\n").map((line, idx) => (
                    <div key={idx} className="terminal-line">{line}</div>
                  ))}
                  {isApplying && <div className="terminal-line">🤖 Agent working... interacting with the page controls...</div>}
                  <div ref={terminalEndRef} />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
