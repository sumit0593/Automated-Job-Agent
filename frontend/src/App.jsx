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
  const [scrapingQuery, setScrapingQuery] = useState("");
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
  const [pipelineMeta, setPipelineMeta] = useState(null);
  const [matchThreshold, setMatchThreshold] = useState(50);
  const [selectedAppId, setSelectedAppId] = useState(null);
  const [appDetail, setAppDetail] = useState(null);
  const [isTailoring, setIsTailoring] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  // User input states for Playwright applying
  const [applicantInfo, setApplicantInfo] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: ""
  });

  // User Profile & Answer Bank states
  const [userProfileData, setUserProfileData] = useState({
    name: "Sumit Kumar",
    email: "sumit@gmail.com",
    phone: "+91 7011676185",
    experience_years: 3.0,
    current_ctc: "₹5 LPA",
    expected_ctc: "₹8 LPA",
    notice_period: "Immediate",
    current_location: "Noida",
    preferred_locations: ["Noida", "Delhi", "Gurgaon", "Remote"],
    work_authorization: "India",
    willing_to_relocate: "Yes",
    remote_preference: "Hybrid"
  });

  const [answerBankData, setAnswerBankData] = useState({
    why_join: "I enjoy building production-grade AI systems, multi-agent frameworks, and scalable cloud architectures.",
    strengths: "Problem solving, backend engineering, GenAI, multi-agent systems, and Python microservices.",
    career_goal: "To become a Lead AI Platform Engineer building scalable agentic systems.",
    why_leaving: "Seeking higher impact roles specializing in Generative AI and Multi-Agent Orchestration."
  });

  // Health check
  const [healthStatus, setHealthStatus] = useState("connecting");

  // Terminal scroll reference
  const terminalEndRef = useRef(null);

  const fetchUserProfile = async () => {
    try {
      const res = await fetch(`${API_BASE}/profile/`);
      if (res.ok) {
        const data = await res.json();
        setUserProfileData(data);
      }
    } catch (e) {
      console.warn("Could not fetch user profile", e);
    }
  };

  const fetchAnswerBank = async () => {
    try {
      const res = await fetch(`${API_BASE}/profile/answers`);
      if (res.ok) {
        const data = await res.json();
        if (data.answers) setAnswerBankData(data.answers);
      }
    } catch (e) {
      console.warn("Could not fetch answer bank", e);
    }
  };

  const handleSaveUserProfile = async (e) => {
    if (e) e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/profile/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(userProfileData)
      });
      if (res.ok) {
        alert("Candidate Profile updated successfully!");
      }
    } catch (e) {
      alert(`Failed to save profile: ${e.message}`);
    }
  };

  const handleSaveAnswerEntry = async (key, value) => {
    try {
      const res = await fetch(`${API_BASE}/profile/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_key: key, stored_answer: value })
      });
      if (res.ok) {
        fetchAnswerBank();
        alert(`Answer for '${key}' updated in Answer Bank!`);
      }
    } catch (e) {
      alert(`Failed to save answer: ${e.message}`);
    }
  };

  useEffect(() => {
    fetchResumes();
    fetchJobs();
    fetchCredentials();
    fetchUserProfile();
    fetchAnswerBank();
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
      const res = await fetch(`${API_BASE}/matching/match?resume_id=${activeResumeId}&min_score=${matchThreshold}`);
      if (res.ok) {
        const data = await res.json();
        setMatches(data.matches || []);
        setPipelineMeta(data.pipeline_meta || null);
        setActiveTab("matching");
      }
    } catch (e) {
      alert(`Matching failed: ${e.message}`);
    } finally {
      setIsMatching(false);
    }
  };

  const getJobApplyType = (url) => {
    if (!url) return "External Website";
    const u = url.toLowerCase();
    if (u.includes("linkedin.com") || u.includes("naukri.com")) return "Easy Apply";
    if (u.includes("greenhouse.io") || u.includes("lever.co") || u.includes("workday") || u.includes("ashbyhq") || u.includes("icims") || u.includes("smartrecruiters") || u.includes("bamboohr") || u.includes("taleo")) return "External Website";
    return "External Website";
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
          phone: applicantInfo.phone,
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
          <User size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          1. Candidate Profile & Accounts
        </button>
        <button 
          className={`tab-btn ${activeTab === 'crawler' ? 'active' : ''}`}
          onClick={() => setActiveTab("crawler")}
        >
          <Search size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          2. Job Discovery Crawler ({jobs.length})
        </button>
        <button 
          className={`tab-btn ${activeTab === 'matching' ? 'active' : ''}`}
          onClick={() => setActiveTab("matching")}
          disabled={!activeResumeId}
        >
          <Briefcase size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          3. Match Rankings ({matches.length})
        </button>
        <button 
          className={`tab-btn ${activeTab === 'applications' ? 'active' : ''}`}
          onClick={() => setActiveTab("applications")}
          disabled={!selectedAppId}
        >
          <Sparkles size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          4. Tailoring & Apply
        </button>
      </div>

      {/* Tab 1: Candidate Profile & Accounts (Merged Tab 1 + Tab 4) */}
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

          {/* Right Column: Personal Profile Data & Stored Answer Bank */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div>
                <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>Candidate Profile (`profile.json`)</h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  Deterministic profile data used for notice period, CTC, locations, and experience questions.
                </p>
              </div>

              <form onSubmit={handleSaveUserProfile} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '160px' }}>
                    <span className="input-label">Full Name</span>
                    <input 
                      type="text" 
                      value={userProfileData.name || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, name: e.target.value })}
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '160px' }}>
                    <span className="input-label">Email Address</span>
                    <input 
                      type="text" 
                      value={userProfileData.email || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, email: e.target.value })}
                      className="input-field" 
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Phone</span>
                    <input 
                      type="text" 
                      value={userProfileData.phone || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, phone: e.target.value })}
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Total Experience (Years)</span>
                    <input 
                      type="number" 
                      step="0.5"
                      value={userProfileData.experience_years || 3.0} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, experience_years: Number(e.target.value) })}
                      className="input-field" 
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Current CTC</span>
                    <input 
                      type="text" 
                      value={userProfileData.current_ctc || "₹5 LPA"} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, current_ctc: e.target.value })}
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Expected CTC</span>
                    <input 
                      type="text" 
                      value={userProfileData.expected_ctc || "₹8 LPA"} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, expected_ctc: e.target.value })}
                      className="input-field" 
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Notice Period</span>
                    <input 
                      type="text" 
                      value={userProfileData.notice_period || "Immediate"} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, notice_period: e.target.value })}
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Current Location</span>
                    <input 
                      type="text" 
                      value={userProfileData.current_location || "Noida"} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, current_location: e.target.value })}
                      className="input-field" 
                    />
                  </div>
                </div>

                <div className="input-group">
                  <span className="input-label">Preferred Locations (Comma separated)</span>
                  <input 
                    type="text" 
                    value={Array.isArray(userProfileData.preferred_locations) ? userProfileData.preferred_locations.join(", ") : (userProfileData.preferred_locations || "")} 
                    onChange={(e) => setUserProfileData({ ...userProfileData, preferred_locations: e.target.value.split(",").map(s => s.trim()) })}
                    className="input-field" 
                  />
                </div>

                <button type="submit" className="btn btn-primary" style={{ marginTop: '0.5rem' }}>
                  Save Candidate Profile Data
                </button>
              </form>
            </div>

            {/* Answer Bank Box */}
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div>
                <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>Answer Bank (`answers.json`)</h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  Zero-LLM instant lookup database for common recruiter interview questions.
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {Object.entries(answerBankData).map(([key, val]) => (
                  <div key={key} className="glass-card" style={{ padding: '0.85rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '0.8rem', color: 'var(--primary)', textTransform: 'capitalize' }}>
                        Question Key: `{key}`
                      </strong>
                      <button 
                        className="btn btn-secondary" 
                        style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}
                        onClick={() => handleSaveAnswerEntry(key, val)}
                      >
                        Save Entry
                      </button>
                    </div>
                    <textarea 
                      rows={2} 
                      value={val || ""} 
                      onChange={(e) => setAnswerBankData({ ...answerBankData, [key]: e.target.value })}
                      className="input-field" 
                      style={{ fontSize: '0.8rem', fontFamily: 'sans-serif' }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Job Discovery Crawler & Match Trigger */}
      {activeTab === "crawler" && (
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div>
            <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>Job Discovery Crawler & Vector Matching</h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
              Find jobs by querying Greenhouse/Lever APIs or using connected accounts to crawl LinkedIn/Naukri, then compute vector similarity rankings.
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

          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <button className="btn btn-primary" onClick={handleScrapeJobs} disabled={isScraping}>
              <Search size={16} />
              {isScraping ? 'Discovering Jobs...' : 'Trigger Crawler Scrape'}
            </button>
          </div>

          {/* Compute Vector Similarity Match CTA Section */}
          <div className="glass-card" style={{ padding: '1.25rem', background: 'rgba(99, 102, 241, 0.08)', border: '1px solid var(--primary-glow)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginTop: '0.5rem' }}>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Sparkles size={18} color="#818cf8" />
                Compute Vector Similarity Match Rankings
              </h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Active Resume: <strong style={{ color: 'var(--primary)' }}>{activeResume ? activeResume.filename : "No CV Selected"}</strong>
                {activeResume && ` (${activeResume.parsed_experience} yrs experience, ${(activeResume.parsed_skills || []).length} skills)`}
              </p>
            </div>
            <button 
              className="btn btn-primary" 
              onClick={handleMatchResume} 
              disabled={isMatching || !activeResumeId}
              style={{ padding: '0.75rem 1.5rem' }}
            >
              {isMatching ? 'Computing Hybrid Vector Rankings...' : '⚡ Compute Match Rankings'}
              <ArrowRight size={16} />
            </button>
          </div>

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
                  <div className="tag-container" style={{ marginTop: '0.75rem', alignItems: 'center' }}>
                    <span className="tag" style={{ background: '#312e81', border: '1px solid #6366f1', color: '#a5b4fc', fontSize: '0.7rem' }}>
                      Apply Type: {getJobApplyType(job.url)}
                    </span>
                    {(job.skills_required || []).map((s, idx) => (
                      <span key={idx} className="tag">{s}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Match Rankings */}
      {activeTab === "matching" && (
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div>
            <h2 className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '0.25rem' }}>
              Agentic RAG Semantic & Hybrid Match Engine
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Multi-stage pipeline: HyDE Query Expansion → Hybrid Vector + Lexical Search → CRAG Adaptive Retries → BGE Cross-Encoder Reranker → MMR Deduplication.
            </p>
          </div>

          {/* RAG Telemetry & Observability Drawer */}
          {pipelineMeta && (
            <div className="glass-card" style={{ padding: '1rem', background: 'rgba(99, 102, 241, 0.05)', borderLeft: '4px solid var(--primary)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <strong style={{ fontSize: '0.8rem', color: 'var(--text-primary)', display: 'block', marginBottom: '0.25rem' }}>RAG Pipeline Analytics & Diagnostics</strong>
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  <span>🎯 Intent: <strong>{pipelineMeta.intent}</strong></span>
                  <span>📄 HyDE: <strong>{pipelineMeta.hyde_generated ? 'Active' : 'N/A'}</strong></span>
                  <span>🔄 Retries: <strong>{pipelineMeta.retrieval_attempts}</strong></span>
                  <span>⚡ Confidence: <strong>{pipelineMeta.confidence_score}%</strong></span>
                </div>
              </div>
              {pipelineMeta.rag_metrics && (
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  <span>📊 Precision@K: <strong>{pipelineMeta.rag_metrics.precision_at_k}%</strong></span>
                  <span>⏱️ Latency: <strong>{pipelineMeta.rag_metrics.retrieval_latency_ms}ms</strong></span>
                  <span>🛡️ Groundedness: <strong>{pipelineMeta.rag_metrics.groundedness_score}%</strong></span>
                </div>
              )}
            </div>
          )}

          {/* Match Score Threshold Filter Slider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', background: 'rgba(15, 23, 42, 0.4)', padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <label style={{ fontSize: '0.85rem', color: 'var(--text-primary)', fontWeight: 600, minWidth: '210px' }}>
              🎯 Match Threshold Filter: <strong style={{ color: 'var(--primary)' }}>{matchThreshold}%</strong>
            </label>
            <input 
              type="range" 
              min="0" 
              max="90" 
              step="5" 
              value={matchThreshold} 
              onChange={(e) => setMatchThreshold(Number(e.target.value))}
              style={{ accentColor: 'var(--primary)', cursor: 'pointer', flex: 1 }}
            />
            <button className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }} onClick={handleMatchResume}>
              Apply Filter
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {matches.map((m, idx) => (
              <div key={idx} className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1.25rem', borderLeft: '4px solid var(--primary)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: '1.25rem', alignItems: 'center' }}>
                    <div className="score-badge" style={{ minWidth: '60px', height: '60px' }}>
                      {m.match_percentage}%
                      <span style={{ display: 'block', fontSize: '0.6rem', color: 'var(--text-muted)', fontWeight: 500 }}>match</span>
                    </div>
                    <div>
                      <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>{m.title}</h3>
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        <strong>{m.company}</strong> • {m.location} {m.created_at ? `• Posted: ${m.created_at}` : ''}
                      </p>
                      <div style={{ marginTop: '0.35rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap', alignItems: 'center' }}>
                        <span className={`status-badge status-${m.status}`}>
                          {m.status}
                        </span>
                        <span className="tag" style={{ background: '#312e81', border: '1px solid #6366f1', color: '#a5b4fc', fontSize: '0.68rem', padding: '0.15rem 0.5rem' }}>
                          Apply Type: {m.application_type || getJobApplyType(m.url)}
                        </span>
                        {m.url && (
                          <a 
                            href={m.url} 
                            target="_blank" 
                            rel="noopener noreferrer" 
                            style={{ fontSize: '0.75rem', color: 'var(--secondary)', textDecoration: 'none', marginLeft: '0.4rem', display: 'inline-flex', alignItems: 'center', gap: '0.2rem' }}
                          >
                            View Job Post ↗
                          </a>
                        )}
                      </div>
                    </div>
                  </div>

                  <button className="btn btn-primary" onClick={() => handleSelectApplication(m.application_id)}>
                    Review & Tailor CV
                    <ArrowRight size={16} />
                  </button>
                </div>

                {/* Granular Sub-Scores */}
                {m.sub_scores && (
                  <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', background: 'rgba(15, 23, 42, 0.5)', padding: '0.6rem 0.85rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                    <span style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>
                      🛠️ Skill Match: <strong style={{ color: 'var(--secondary)' }}>{m.sub_scores.skill_match_pct}%</strong>
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>
                      💼 Experience Match: <strong style={{ color: 'var(--success)' }}>{m.sub_scores.experience_match_pct}%</strong>
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>
                      🧠 Semantic Similarity: <strong style={{ color: '#a5b4fc' }}>{m.sub_scores.semantic_similarity_pct}%</strong>
                    </span>
                  </div>
                )}

                {/* Missing Skills Tag List */}
                {m.missing_skills && m.missing_skills.length > 0 && (
                  <div>
                    <strong style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Missing Skill Gaps Flagged:</strong>
                    <div className="tag-container" style={{ marginTop: '0.25rem' }}>
                      {m.missing_skills.map((sk, skIdx) => (
                        <span key={skIdx} className="tag" style={{ color: '#f87171', background: 'rgba(239, 68, 68, 0.08)', borderColor: 'rgba(239, 68, 68, 0.25)' }}>
                          {sk}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Grounded Selection Explanations */}
                {m.why_selected && m.why_selected.length > 0 && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: '0.25rem' }}>Why this job was selected:</strong>
                    <ul style={{ paddingLeft: '1.25rem', margin: 0 }}>
                      {m.why_selected.map((reason, rIdx) => (
                        <li key={rIdx} style={{ marginBottom: '0.2rem' }}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}

            {matches.length === 0 && (
              <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                <AlertCircle size={48} style={{ margin: '0 auto 1rem', display: 'block' }} />
                <p>No job matches found meeting your <strong>{matchThreshold}%</strong> threshold filter requirement.</p>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                  Try lowering the Match Threshold slider above and clicking <strong>Apply Filter</strong>.
                </p>
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
                <span className="tag" style={{ background: '#312e81', border: '1px solid #6366f1', color: '#a5b4fc' }}>
                  Type: {appDetail.application_type || "Unknown"}
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
              <div className="input-group" style={{ flex: 1.5, minWidth: '200px' }}>
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
              <div className="input-group" style={{ flex: 1.5, minWidth: '200px' }}>
                <span className="input-label">Phone Number</span>
                <div style={{ position: 'relative' }}>
                  <User size={16} style={{ position: 'absolute', left: '10px', top: '12px', color: 'var(--text-muted)' }} />
                  <input 
                    type="text" 
                    value={applicantInfo.phone}
                    onChange={(e) => setApplicantInfo({ ...applicantInfo, phone: e.target.value })}
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
