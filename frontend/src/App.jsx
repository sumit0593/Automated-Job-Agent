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
  ShieldCheck,
  Clock,
  Calendar,
  Activity,
  Plus,
  PlayCircle,
  StopCircle,
  Check,
  XCircle
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
    name: "",
    email: "",
    country_code: "+91",
    phone: "",
    pan_number: "",
    date_of_birth: "",
    last_working_day: "",
    experience_years: 0.0,
    current_ctc: "",
    expected_ctc: "",
    notice_period: "",
    current_location: "",
    preferred_locations: [],
    skills: [],
    linkedin_url: "",
    github_url: "",
    portfolio_url: "",
    work_authorization: "",
    willing_to_relocate: "",
    remote_preference: ""
  });

  const [answerBankData, setAnswerBankData] = useState({
    why_join: "I enjoy building production-grade AI systems, multi-agent frameworks, and scalable cloud architectures.",
    strengths: "Problem solving, backend engineering, GenAI, multi-agent systems, and Python microservices.",
    career_goal: "To become a Lead AI Platform Engineer building scalable agentic systems.",
    why_leaving: "Seeking higher impact roles specializing in Generative AI and Multi-Agent Orchestration."
  });

  // Scheduler & Queue states
  const [schedulerStatus, setSchedulerStatus] = useState({ running: false, scheduled_jobs: 0 });
  const [schedulesList, setSchedulesList] = useState([]);
  const [schedulerTasks, setSchedulerTasks] = useState([]);
  const [rateLimitStats, setRateLimitStats] = useState({});
  const [isScheduling, setIsScheduling] = useState(false);
  const [scheduleForm, setScheduleForm] = useState({
    selectedPlatforms: ["naukri", "linkedin"],
    keyword: "GenAI Engineer",
    locationsInput: "Remote, Noida, Bengaluru",
    preset: "0 9,18 * * 1-5",
    customCron: "0 9,18 * * 1-5",
    maxJobs: 25,
    autoApply: true,
    minMatchScore: 70
  });

  const [appFilter, setAppFilter] = useState('all');
  const [selectedMatchIds, setSelectedMatchIds] = useState(new Set());
  const [isBatchApplying, setIsBatchApplying] = useState(false);

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

  const fetchSchedulerData = async () => {
    try {
      const [statusRes, schedRes, tasksRes, limitsRes] = await Promise.all([
        fetch(`${API_BASE}/schedule/status`),
        fetch(`${API_BASE}/schedule/schedules`),
        fetch(`${API_BASE}/schedule/tasks?limit=20`),
        fetch(`${API_BASE}/schedule/rate-limits`)
      ]);
      if (statusRes.ok) {
        const data = await statusRes.json();
        setSchedulerStatus(data);
        setHealthStatus("online");
      }
      if (schedRes.ok) {
        const data = await schedRes.json();
        setSchedulesList(data.schedules || []);
      }
      if (tasksRes.ok) {
        const data = await tasksRes.json();
        setSchedulerTasks(data.tasks || []);
      }
      if (limitsRes.ok) {
        const data = await limitsRes.json();
        setRateLimitStats(data || {});
      }
    } catch (e) {
      console.warn("Could not fetch scheduler data", e);
    }
  };

  const handleToggleSchedulePlatform = (plat) => {
    setScheduleForm(prev => {
      const exists = prev.selectedPlatforms.includes(plat);
      if (exists) {
        if (prev.selectedPlatforms.length === 1) return prev;
        return { ...prev, selectedPlatforms: prev.selectedPlatforms.filter(p => p !== plat) };
      } else {
        return { ...prev, selectedPlatforms: [...prev.selectedPlatforms, plat] };
      }
    });
  };

  const handleCreateSchedule = async (e) => {
    e.preventDefault();
    if (!scheduleForm.keyword.trim()) {
      alert("Please enter a search keyword.");
      return;
    }
    if (scheduleForm.selectedPlatforms.length === 0) {
      alert("Please select at least one job platform.");
      return;
    }

    const cronExpr = scheduleForm.preset === "custom" ? scheduleForm.customCron : scheduleForm.preset;
    setIsScheduling(true);

    try {
      const res = await fetch(`${API_BASE}/schedule/discovery`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platforms: scheduleForm.selectedPlatforms,
          keyword: scheduleForm.keyword.trim(),
          locations: scheduleForm.locationsInput.split(",").map(s => s.trim()).filter(Boolean),
          cron_expression: cronExpr,
          max_jobs: parseInt(scheduleForm.maxJobs, 10),
          auto_apply: scheduleForm.autoApply,
          min_match_score: scheduleForm.minMatchScore
        })
      });

      if (res.ok) {
        const data = await res.json();
        await fetchSchedulerData();
        setIsScheduling(false);
        setTimeout(() => {
          alert(`Successfully scheduled ${data.count} recurring discovery task(s)!`);
        }, 50);
      } else {
        const err = await res.json();
        setIsScheduling(false);
        alert(`Failed to create schedule: ${err.detail || "Server error"}`);
      }
    } catch (err) {
      setIsScheduling(false);
      alert(`Error creating schedule: ${err.message}`);
    }
  };

  const handleRemoveSchedule = async (jobId) => {
    if (!confirm(`Are you sure you want to remove recurring schedule '${jobId}'?`)) return;
    try {
      const res = await fetch(`${API_BASE}/schedule/${encodeURIComponent(jobId)}`, { method: "DELETE" });
      if (res.ok) {
        fetchSchedulerData();
      }
    } catch (err) {
      alert(`Error removing schedule: ${err.message}`);
    }
  };

  const handleStartScheduler = async () => {
    try {
      const res = await fetch(`${API_BASE}/schedule/start`, { method: "POST" });
      if (res.ok) {
        fetchSchedulerData();
      }
    } catch (err) {
      alert(`Error starting scheduler: ${err.message}`);
    }
  };

  const handleStopScheduler = async () => {
    try {
      const res = await fetch(`${API_BASE}/schedule/stop`, { method: "POST" });
      if (res.ok) {
        fetchSchedulerData();
      }
    } catch (err) {
      alert(`Error stopping scheduler: ${err.message}`);
    }
  };

  const handleCancelTask = async (taskId) => {
    try {
      const res = await fetch(`${API_BASE}/schedule/tasks/${taskId}`, { method: "DELETE" });
      if (res.ok) {
        fetchSchedulerData();
      }
    } catch (err) {
      alert(`Error cancelling task: ${err.message}`);
    }
  };

  const handleClearAllSchedules = async () => {
    if (!confirm("Are you sure you want to delete ALL recurring discovery schedules?")) return;
    try {
      const res = await fetch(`${API_BASE}/schedule/schedules/all`, { method: "DELETE" });
      if (res.ok) {
        const data = await res.json();
        alert(`Cleared ${data.count} recurring schedules.`);
        fetchSchedulerData();
      }
    } catch (err) {
      alert(`Error clearing schedules: ${err.message}`);
    }
  };

  const handleResetRateLimits = async () => {
    if (!confirm("Are you sure you want to reset all platform rate limit counters? (Useful for testing)")) return;
    try {
      const res = await fetch(`${API_BASE}/schedule/rate-limits/reset`, { method: "POST" });
      if (res.ok) {
        alert("Platform rate limit counters reset successfully!");
        fetchSchedulerData();
      }
    } catch (err) {
      alert(`Error resetting rate limits: ${err.message}`);
    }
  };

  const handleClearTaskHistory = async () => {
    if (!confirm("Are you sure you want to clear completed, failed, and cancelled task history?")) return;
    try {
      const res = await fetch(`${API_BASE}/schedule/tasks/history`, { method: "DELETE" });
      if (res.ok) {
        const data = await res.json();
        alert(`Cleared ${data.count} task execution logs.`);
        fetchSchedulerData();
      }
    } catch (err) {
      alert(`Error clearing task history: ${err.message}`);
    }
  };

  useEffect(() => {
    fetchResumes();
    fetchJobs();
    fetchCredentials();
    fetchUserProfile();
    fetchAnswerBank();
    fetchSchedulerData();
    checkHealth();

    const healthInterval = setInterval(checkHealth, 10000);
    return () => clearInterval(healthInterval);
  }, []);

  // Poll scheduler tab data if active
  useEffect(() => {
    let intervalId;
    if (activeTab === "scheduler") {
      fetchSchedulerData();
      intervalId = setInterval(fetchSchedulerData, 10000);
    }
    return () => clearInterval(intervalId);
  }, [activeTab]);

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

  const [isUploadingCv, setIsUploadingCv] = useState(false);
  const [uploadStageText, setUploadStageText] = useState("⚡ Indexing PDF sections & vectorizing with BGE-M3...");

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setIsUploadingCv(true);
    setUploadStageText("⚡ Extracting PDF text & building semantic sections...");

    // Stage text timer
    const t1 = setTimeout(() => {
      setUploadStageText("🧠 Running Dense BGE-M3 Vector Store indexing...");
    }, 1800);
    const t2 = setTimeout(() => {
      setUploadStageText("🔍 Grounded RAG Extraction (BM25 + Cross-Encoder Reranker)...");
    }, 4500);

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
        await fetchUserProfile();
        await fetchAnswerBank();
        alert("✅ Resume successfully uploaded, parsed, and synced to Candidate Profile!");
      } else {
        const err = await res.json();
        alert(`Parsing failed: ${err.detail || "Server error"}`);
      }
    } catch (err) {
      alert(`Upload error: ${err.message}`);
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      setIsUploadingCv(false);
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

  // Batch Selection Helpers
  const toggleMatchSelection = (appId) => {
    setSelectedMatchIds(prev => {
      const next = new Set(prev);
      if (next.has(appId)) next.delete(appId);
      else next.add(appId);
      return next;
    });
  };

  const toggleSelectAllMatches = (filteredMatches) => {
    const allIds = filteredMatches.map(m => m.application_id).filter(Boolean);
    const allSelected = allIds.length > 0 && allIds.every(id => selectedMatchIds.has(id));
    if (allSelected) {
      setSelectedMatchIds(new Set());
    } else {
      setSelectedMatchIds(new Set(allIds));
    }
  };

  const handleBatchApply = async () => {
    const ids = Array.from(selectedMatchIds).filter(Boolean);
    if (ids.length === 0) return;
    setIsBatchApplying(true);
    try {
      const res = await fetch(`${API_BASE}/schedule/batch-apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ application_ids: ids, delay_minutes: 0 })
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedMatchIds(new Set());
        alert(`✅ ${ids.length} job(s) queued for auto-apply! They will be processed sequentially (3 min apart).`);
      } else {
        const err = await res.json();
        alert(`Failed to queue batch: ${err.detail || "Server error"}`);
      }
    } catch (err) {
      alert(`Batch apply error: ${err.message}`);
    } finally {
      setIsBatchApplying(false);
    }
  };

  const handleClearMatches = async () => {
    if (!window.confirm("Are you sure you want to clear all matched applications from Tab 3?")) return;
    try {
      const res = await fetch(`${API_BASE}/matching/clear`, { method: "POST" });
      if (res.ok) {
        setMatches([]);
        setSelectedMatchIds(new Set());
        alert("✅ Tab 3 match records successfully cleared!");
      }
    } catch (err) {
      alert(`Clear matches failed: ${err.message}`);
    }
  };

  const handleClearProfile = async () => {
    if (!window.confirm("Are you sure you want to clear your Candidate Profile, Answer Bank, and Match Results? This action will reset all stored profile fields and match records.")) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/profile/clear`, { method: "POST" });
      await fetch(`${API_BASE}/matching/clear`, { method: "POST" });
      if (res.ok) {
        setUserProfileData({
          name: "",
          email: "",
          country_code: "+91",
          phone: "",
          pan_number: "",
          date_of_birth: "",
          last_working_day: "",
          experience_years: 0.0,
          current_ctc: "",
          expected_ctc: "",
          notice_period: "",
          current_location: "",
          preferred_locations: [],
          skills: [],
          linkedin_url: "",
          github_url: "",
          portfolio_url: "",
          work_authorization: "",
          willing_to_relocate: "",
          remote_preference: ""
        });
        setAnswerBankData({});
        setMatches([]);
        setSelectedMatchIds(new Set());
        alert("✅ Candidate Profile, Answer Bank, and Match Results have been safely reset!");
      } else {
        alert("Failed to clear profile data.");
      }
    } catch (err) {
      alert(`Clear failed: ${err.message}`);
    }
  };

  const handleReextractProfile = async (resumeId) => {
    const targetId = resumeId || activeResumeId;
    if (!targetId) {
      alert("Please upload or select a resume first.");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/resumes/${targetId}/extract-profile`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.profile) setUserProfileData(data.profile);
        if (data.answers) setAnswerBankData(data.answers);
        alert(`✅ Re-extracted candidate profile & answer bank from resume using Hybrid RAG!`);
      } else {
        alert("Failed to extract profile from resume.");
      }
    } catch (err) {
      alert(`Extraction failed: ${err.message}`);
    }
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
        <button 
          className={`tab-btn ${activeTab === 'scheduler' ? 'active' : ''}`}
          onClick={() => setActiveTab("scheduler")}
        >
          <Clock size={18} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          5. Scheduler & Automation ({schedulesList.length})
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
              
              <div 
                className="upload-zone" 
                onClick={() => !isUploadingCv && document.getElementById('pdf-file-input').click()}
                style={{
                  cursor: isUploadingCv ? 'wait' : 'pointer',
                  borderColor: isUploadingCv ? 'var(--primary)' : undefined,
                  background: isUploadingCv ? 'rgba(99, 102, 241, 0.12)' : undefined,
                  pointerEvents: isUploadingCv ? 'none' : 'auto'
                }}
              >
                {isUploadingCv ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 0' }}>
                    <div className="spinner" style={{ width: '36px', height: '36px', border: '3px solid rgba(99,102,241,0.25)', borderTopColor: '#818cf8', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                    <p style={{ fontWeight: 700, fontSize: '0.9rem', color: '#a5b4fc' }}>Processing & Indexing Resume...</p>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', animation: 'pulse 1.5s infinite alternate', textAlign: 'center' }}>
                      {uploadStageText}
                    </p>
                  </div>
                ) : (
                  <>
                    <UploadCloud className="upload-icon" />
                    <p style={{ fontWeight: 600, fontSize: '0.95rem' }}>Upload CV (PDF format)</p>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.25rem' }}>BGE-M3 local indexing on upload</p>
                  </>
                )}
                <input 
                  id="pdf-file-input"
                  type="file" 
                  accept="application/pdf"
                  onChange={handleFileUpload} 
                  disabled={isUploadingCv}
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
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.4rem' }}>
                  {['linkedin', 'naukri', 'glassdoor', 'indeed', 'wellfound', 'workday'].map((plat) => (
                    <button 
                      key={plat}
                      type="button"
                      className={`btn ${newCred.platform === plat ? 'btn-primary' : ''}`}
                      onClick={() => setNewCred({ ...newCred, platform: plat })}
                      style={{ padding: '0.4rem 0.25rem', fontSize: '0.75rem', textTransform: 'capitalize' }}
                    >
                      {plat === 'linkedin' ? 'LinkedIn' : plat === 'naukri' ? 'Naukri' : plat}
                    </button>
                  ))}
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>
                  💡 <strong>Public ATS Notice:</strong> Greenhouse, Lever, Ashby, and SmartRecruiters forms submit directly using your Candidate Profile without requiring account logins.
                </p>

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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div>
                  <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>Candidate Profile (`profile.json`)</h2>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                    Grounded profile data extracted via Hybrid RAG (Dense + BM25 + Cross-Encoder) — zero fake data.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button 
                    type="button" 
                    className="btn btn-secondary" 
                    style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
                    onClick={() => handleReextractProfile(activeResumeId)}
                    title="Re-run Hybrid RAG Extraction over selected resume"
                  >
                    ⚡ Re-extract from CV
                  </button>
                  <button 
                    type="button" 
                    className="btn" 
                    style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem', background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                    onClick={handleClearProfile}
                    title="Safely reset all candidate profile and answer bank records in DB"
                  >
                    🗑️ Clear Profile & Answer Bank
                  </button>
                </div>
              </div>

              <form onSubmit={handleSaveUserProfile} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '160px' }}>
                    <span className="input-label">Full Name</span>
                    <input 
                      type="text" 
                      value={userProfileData.name || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, name: e.target.value })}
                      placeholder="e.g. Sumit Kumar"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '160px' }}>
                    <span className="input-label">Email Address</span>
                    <input 
                      type="text" 
                      value={userProfileData.email || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, email: e.target.value })}
                      placeholder="email@example.com"
                      className="input-field" 
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ width: '100px' }}>
                    <span className="input-label">Country Code</span>
                    <input 
                      type="text" 
                      value={userProfileData.country_code || "+91"} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, country_code: e.target.value })}
                      placeholder="+91"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Phone</span>
                    <input 
                      type="text" 
                      value={userProfileData.phone || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, phone: e.target.value })}
                      placeholder="7011676185"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Total Experience (Years)</span>
                    <input 
                      type="number" 
                      step="0.5"
                      value={userProfileData.experience_years || 0.0} 
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
                      value={userProfileData.current_ctc || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, current_ctc: e.target.value })}
                      placeholder="e.g. ₹7 LPA"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Expected CTC</span>
                    <input 
                      type="text" 
                      value={userProfileData.expected_ctc || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, expected_ctc: e.target.value })}
                      placeholder="e.g. ₹12 LPA"
                      className="input-field" 
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '130px' }}>
                    <span className="input-label">PAN Card No.</span>
                    <input 
                      type="text" 
                      value={userProfileData.pan_number || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, pan_number: e.target.value })}
                      placeholder="e.g. ABCDE1234F"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '130px' }}>
                    <span className="input-label">Date of Birth (DOB)</span>
                    <input 
                      type="text" 
                      value={userProfileData.date_of_birth || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, date_of_birth: e.target.value })}
                      placeholder="DD/MM/YYYY"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '130px' }}>
                    <span className="input-label">Last Working Day (LWD)</span>
                    <input 
                      type="text" 
                      value={userProfileData.last_working_day || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, last_working_day: e.target.value })}
                      placeholder="e.g. 31/08/2026 or N/A"
                      className="input-field" 
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Notice Period</span>
                    <input 
                      type="text" 
                      value={userProfileData.notice_period || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, notice_period: e.target.value })}
                      placeholder="e.g. Immediate / 30 Days"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '140px' }}>
                    <span className="input-label">Current Location</span>
                    <input 
                      type="text" 
                      value={userProfileData.current_location || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, current_location: e.target.value })}
                      placeholder="e.g. Noida"
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

                {/* Social Profiles & Portfolio Links */}
                <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', borderTop: '1px solid var(--border-color)', paddingTop: '0.85rem' }}>
                  <div className="input-group" style={{ flex: 1, minWidth: '160px' }}>
                    <span className="input-label">LinkedIn URL</span>
                    <input 
                      type="text" 
                      value={userProfileData.linkedin_url || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, linkedin_url: e.target.value })}
                      placeholder="linkedin.com/in/username"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '160px' }}>
                    <span className="input-label">GitHub URL</span>
                    <input 
                      type="text" 
                      value={userProfileData.github_url || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, github_url: e.target.value })}
                      placeholder="github.com/username"
                      className="input-field" 
                    />
                  </div>
                  <div className="input-group" style={{ flex: 1, minWidth: '160px' }}>
                    <span className="input-label">Portfolio URL</span>
                    <input 
                      type="text" 
                      value={userProfileData.portfolio_url || ""} 
                      onChange={(e) => setUserProfileData({ ...userProfileData, portfolio_url: e.target.value })}
                      placeholder="portfolio.vercel.app"
                      className="input-field" 
                    />
                  </div>
                </div>

                {/* Skills Tags Tab / Container */}
                <div className="input-group" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.85rem' }}>
                  <span className="input-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Candidate Core Skills ({Array.isArray(userProfileData.skills) ? userProfileData.skills.length : 0})</span>
                  </span>
                  <div className="tag-container" style={{ minHeight: '42px', padding: '0.5rem', background: 'rgba(15, 23, 42, 0.6)', border: '1px solid var(--border-color)', borderRadius: '8px', display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                    {Array.isArray(userProfileData.skills) && userProfileData.skills.length > 0 ? (
                      userProfileData.skills.map((sk, idx) => (
                        <span key={idx} className="tag" style={{ background: '#312e81', borderColor: '#6366f1', color: '#a5b4fc', fontSize: '0.75rem', padding: '0.2rem 0.6rem', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
                          {sk}
                          <button 
                            type="button" 
                            style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', padding: 0, fontSize: '0.8rem', fontWeight: 700 }}
                            onClick={() => {
                              const updated = userProfileData.skills.filter((_, i) => i !== idx);
                              setUserProfileData({ ...userProfileData, skills: updated });
                            }}
                          >
                            ×
                          </button>
                        </span>
                      ))
                    ) : (
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No skills added yet. Upload a CV or enter skills separated by commas below.</span>
                    )}
                  </div>
                  <input 
                    type="text" 
                    placeholder="Type skills comma separated to add/edit (e.g. Python, FastAPI, React)..."
                    value={Array.isArray(userProfileData.skills) ? userProfileData.skills.join(", ") : ""} 
                    onChange={(e) => setUserProfileData({ ...userProfileData, skills: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })}
                    className="input-field" 
                    style={{ marginTop: '0.35rem' }}
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
                <option value="">All Job Boards & Public ATS (Auto-Detect)</option>
                <option value="naukri">Naukri Crawler</option>
                <option value="linkedin">LinkedIn Crawler</option>
                <option value="indeed">Indeed Search (API/Web)</option>
                <option value="wellfound">Wellfound (Startup Jobs)</option>
                <option value="glassdoor">Glassdoor Jobs</option>
                <option value="workday">Workday ATS</option>
                <option value="greenhouse">Greenhouse ATS</option>
                <option value="lever">Lever ATS</option>
                <option value="ashby">Ashby ATS</option>
                <option value="smartrecruiters">SmartRecruiters ATS</option>
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <h2 className="gradient-text" style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '0.25rem' }}>
                Agentic RAG Semantic & Hybrid Match Engine
              </h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                Multi-stage pipeline: HyDE Query Expansion → Hybrid Vector + Lexical Search → CRAG Adaptive Retries → BGE Cross-Encoder Reranker → MMR Deduplication.
              </p>
            </div>
            {matches.length > 0 && (
              <button 
                type="button" 
                className="btn" 
                style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem', background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                onClick={handleClearMatches}
                title="Wipe all Tab 3 match records"
              >
                🗑️ Clear Match Results
              </button>
            )}
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

          {/* Application Status Metrics Breakdown Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <div 
              className="stat-card" 
              onClick={() => setAppFilter('applied')}
              style={{ borderLeft: '3px solid #10b981', cursor: 'pointer', background: appFilter === 'applied' ? 'rgba(16, 185, 129, 0.15)' : 'var(--bg-surface-elevated)' }}
            >
              <span className="stat-label" style={{ color: '#10b981' }}>✅ APPLIED (SUCCESS)</span>
              <span className="stat-value" style={{ color: '#10b981' }}>
                {matches.filter(m => m.status === 'applied').length}
              </span>
            </div>
            <div 
              className="stat-card" 
              onClick={() => setAppFilter('failed')}
              style={{ borderLeft: '3px solid #f87171', cursor: 'pointer', background: appFilter === 'failed' ? 'rgba(239, 68, 68, 0.15)' : 'var(--bg-surface-elevated)' }}
            >
              <span className="stat-label" style={{ color: '#f87171' }}>❌ FAILED / ERROR</span>
              <span className="stat-value" style={{ color: '#f87171' }}>
                {matches.filter(m => m.status === 'failed').length}
              </span>
            </div>
            <div 
              className="stat-card" 
              onClick={() => setAppFilter('pending')}
              style={{ borderLeft: '3px solid #f59e0b', cursor: 'pointer', background: appFilter === 'pending' ? 'rgba(245, 158, 11, 0.15)' : 'var(--bg-surface-elevated)' }}
            >
              <span className="stat-label" style={{ color: '#f59e0b' }}>⏳ PENDING / QUEUED</span>
              <span className="stat-value" style={{ color: '#f59e0b' }}>
                {matches.filter(m => m.status === 'pending' || m.status === 'in_progress' || m.status === 'applying').length}
              </span>
            </div>
            <div 
              className="stat-card" 
              onClick={() => setAppFilter('all')}
              style={{ borderLeft: '3px solid var(--primary)', cursor: 'pointer', background: appFilter === 'all' ? 'rgba(99, 102, 241, 0.15)' : 'var(--bg-surface-elevated)' }}
            >
              <span className="stat-label">TOTAL MATCHED</span>
              <span className="stat-value">{matches.length}</span>
            </div>
          </div>

          {/* Match Score Threshold Filter Slider & Status Filter Bar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', background: 'rgba(15, 23, 42, 0.4)', padding: '0.85rem 1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
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

            {/* Status Filter Tab Buttons & Select All Header */}
            {(() => {
              const thresholdMatches = matches.filter(m => Number(m.match_percentage || 0) >= matchThreshold);
              const getStatusMatches = (filterType) => {
                return thresholdMatches.filter(m => {
                  if (filterType === 'applied') return m.status === 'applied';
                  if (filterType === 'failed') return m.status === 'failed';
                  if (filterType === 'pending') return m.status === 'pending' || m.status === 'in_progress' || m.status === 'applying';
                  return true;
                });
              };
              const visibleMatches = getStatusMatches(appFilter);

              return (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      <button 
                        className="btn" 
                        onClick={() => setAppFilter('all')}
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.65rem', background: appFilter === 'all' ? 'var(--primary)' : 'var(--bg-surface)', borderColor: appFilter === 'all' ? 'var(--primary)' : 'var(--border-color)' }}
                      >
                        All Applications ({thresholdMatches.length})
                      </button>
                      <button 
                        className="btn" 
                        onClick={() => setAppFilter('applied')}
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.65rem', background: appFilter === 'applied' ? 'rgba(16, 185, 129, 0.2)' : 'var(--bg-surface)', color: appFilter === 'applied' ? '#34d399' : 'var(--text-secondary)', borderColor: appFilter === 'applied' ? '#10b981' : 'var(--border-color)' }}
                      >
                        ✅ Applied ({getStatusMatches('applied').length})
                      </button>
                      <button 
                        className="btn" 
                        onClick={() => setAppFilter('failed')}
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.65rem', background: appFilter === 'failed' ? 'rgba(239, 68, 68, 0.2)' : 'var(--bg-surface)', color: appFilter === 'failed' ? '#f87171' : 'var(--text-secondary)', borderColor: appFilter === 'failed' ? '#ef4444' : 'var(--border-color)' }}
                      >
                        ❌ Failed ({getStatusMatches('failed').length})
                      </button>
                      <button 
                        className="btn" 
                        onClick={() => setAppFilter('pending')}
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.65rem', background: appFilter === 'pending' ? 'rgba(245, 158, 11, 0.2)' : 'var(--bg-surface)', color: appFilter === 'pending' ? '#fbbf24' : 'var(--text-secondary)', borderColor: appFilter === 'pending' ? '#f59e0b' : 'var(--border-color)' }}
                      >
                        ⏳ Pending ({getStatusMatches('pending').length})
                      </button>
                    </div>

                    {/* Select All Checkbox Control */}
                    {visibleMatches.length > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', userSelect: 'none' }}>
                          <input 
                            type="checkbox"
                            checked={
                              visibleMatches
                                .map(m => m.application_id)
                                .filter(Boolean)
                                .every(id => selectedMatchIds.has(id)) && visibleMatches.length > 0
                            }
                            onChange={() => toggleSelectAllMatches(visibleMatches)}
                            style={{ width: '16px', height: '16px', accentColor: 'var(--primary)', cursor: 'pointer' }}
                          />
                          <strong>Select All Rows ({visibleMatches.length})</strong>
                        </label>
                        {selectedMatchIds.size > 0 && (
                          <span style={{ color: 'var(--primary)', fontWeight: 600 }}>({selectedMatchIds.size} selected)</span>
                        )}
                      </div>
                    )}
                  </div>
                </>
              );
            })()}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {matches
              .filter(m => Number(m.match_percentage || 0) >= matchThreshold)
              .filter(m => {
                if (appFilter === 'applied') return m.status === 'applied';
                if (appFilter === 'failed') return m.status === 'failed';
                if (appFilter === 'pending') return m.status === 'pending' || m.status === 'in_progress' || m.status === 'applying';
                return true;
              })
              .map((m, idx) => (
              <div key={idx} className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1.25rem', borderLeft: `4px solid ${m.status === 'applied' ? '#10b981' : m.status === 'failed' ? '#ef4444' : 'var(--primary)'}`, background: selectedMatchIds.has(m.application_id) ? 'rgba(99, 102, 241, 0.08)' : undefined }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    {/* Multi-Select Checkbox */}
                    {m.application_id && (
                      <input 
                        type="checkbox"
                        checked={selectedMatchIds.has(m.application_id)}
                        onChange={() => toggleMatchSelection(m.application_id)}
                        style={{ width: '18px', height: '18px', accentColor: 'var(--primary)', cursor: 'pointer', flexShrink: 0 }}
                      />
                    )}

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

          {/* Floating Batch Action Bar */}
          {selectedMatchIds.size > 0 && (
            <div style={{
              position: 'sticky',
              bottom: '1.5rem',
              zIndex: 100,
              background: 'rgba(15, 23, 42, 0.95)',
              backdropFilter: 'blur(12px)',
              border: '2px solid var(--primary)',
              borderRadius: '12px',
              padding: '0.85rem 1.5rem',
              display: 'flex',
              justify: 'space-between',
              alignItems: 'center',
              boxShadow: '0 10px 25px -5px rgba(99, 102, 241, 0.4)',
              gap: '1rem'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontSize: '1.25rem' }}>⚡</span>
                <div>
                  <strong style={{ fontSize: '0.9rem', color: '#fff', display: 'block' }}>
                    {selectedMatchIds.size} Job{selectedMatchIds.size > 1 ? 's' : ''} Selected
                  </strong>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    Ready for sequential auto-application pipeline
                  </span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                <button 
                  className="btn btn-secondary" 
                  style={{ fontSize: '0.78rem', padding: '0.4rem 0.85rem' }}
                  onClick={() => setSelectedMatchIds(new Set())}
                >
                  Clear Selection
                </button>
                <button 
                  className="btn btn-primary" 
                  disabled={isBatchApplying}
                  onClick={handleBatchApply}
                  style={{ fontSize: '0.85rem', padding: '0.45rem 1.1rem', background: 'linear-[#6366f1, #4f46e5]', border: 'none' }}
                >
                  {isBatchApplying ? 'Queueing Applications...' : `🚀 Batch Apply (${selectedMatchIds.size})`}
                </button>
              </div>
            </div>
          )}
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

      {/* Tab 5: Scheduler & Automation */}
      {activeTab === "scheduler" && (
        <div className="scheduler-dashboard">
          {/* Header & Status Control Bar */}
          <div className="glass-panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Clock size={20} />
                Automated Task Scheduler & Cron Engine
              </h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Schedule recurring background discovery scans across multiple job boards & locations using APScheduler + SQLite Queue.
              </p>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Worker Engine:</span>
                <span className={`badge-status ${schedulerStatus.running ? 'healthy' : 'failed'}`}>
                  {schedulerStatus.running ? '🟢 RUNNING' : '🔴 STOPPED'}
                </span>
              </div>

              {schedulerStatus.running ? (
                <button className="btn" onClick={handleStopScheduler} style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)', padding: '0.4rem 0.85rem' }}>
                  <StopCircle size={14} /> Stop Scheduler
                </button>
              ) : (
                <button className="btn btn-primary" onClick={handleStartScheduler} style={{ padding: '0.4rem 0.85rem' }}>
                  <PlayCircle size={14} /> Start Scheduler
                </button>
              )}

              <button className="btn" onClick={fetchSchedulerData} style={{ padding: '0.4rem 0.85rem' }}>
                <RefreshCw size={14} /> Sync Status
              </button>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="stat-card-row">
            <div className="stat-card">
              <div className="stat-card-lbl">Active Schedules</div>
              <div className="stat-card-val" style={{ color: 'var(--primary)' }}>{schedulesList.length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-lbl">Pending Tasks</div>
              <div className="stat-card-val" style={{ color: 'var(--warning)' }}>{schedulerStatus.queue_stats?.pending || 0}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-lbl">Running Tasks</div>
              <div className="stat-card-val" style={{ color: 'var(--success)' }}>{schedulerStatus.queue_stats?.running || 0}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-lbl">Completed Tasks</div>
              <div className="stat-card-val" style={{ color: 'var(--text-primary)' }}>{schedulerStatus.queue_stats?.completed || 0}</div>
            </div>
          </div>

          {/* Main Grid: Form + Active Schedules List */}
          <div className="scheduler-grid">
            {/* Panel 1: Create Schedule */}
            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)' }}>
                <Plus size={16} />
                Create Discovery Cron Job
              </h3>

              <form onSubmit={handleCreateSchedule} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {/* Multi-Platform Chips */}
                <div className="input-group">
                  <span className="input-label">Select Target Job Boards</span>
                  <div className="platform-chips">
                    {[
                      { id: 'naukri', label: 'Naukri' },
                      { id: 'linkedin', label: 'LinkedIn' },
                      { id: 'indeed', label: 'Indeed (API)', disabled: false },
                      { id: 'wellfound', label: 'Wellfound (Startup)', disabled: false }
                    ].map(p => (
                      <div 
                        key={p.id}
                        className={`platform-chip ${scheduleForm.selectedPlatforms.includes(p.id) ? 'selected' : ''} ${p.disabled ? 'disabled' : ''}`}
                        onClick={() => !p.disabled && handleToggleSchedulePlatform(p.id)}
                      >
                        {scheduleForm.selectedPlatforms.includes(p.id) && <Check size={12} style={{ display: 'inline', marginRight: '4px' }} />}
                        {p.label}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Keyword */}
                <div className="input-group">
                  <span className="input-label">Search Keyword / Role</span>
                  <input 
                    type="text"
                    value={scheduleForm.keyword}
                    onChange={(e) => setScheduleForm({ ...scheduleForm, keyword: e.target.value })}
                    placeholder="e.g. GenAI Engineer, Python Developer"
                    className="input-field"
                    required
                  />
                </div>

                {/* Locations (Comma separated) */}
                <div className="input-group">
                  <span className="input-label">Locations (Comma-Separated for Multi-Location Scans)</span>
                  <input 
                    type="text"
                    value={scheduleForm.locationsInput}
                    onChange={(e) => setScheduleForm({ ...scheduleForm, locationsInput: e.target.value })}
                    placeholder="e.g. Remote, Noida, Bengaluru, Delhi NCR"
                    className="input-field"
                  />
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Tip: Enqueues distinct, staggered discovery scans for each location.
                  </span>
                </div>

                {/* Cron Presets */}
                <div className="input-group">
                  <span className="input-label">Frequency / Schedule Preset</span>
                  <select 
                    className="input-field"
                    value={scheduleForm.preset}
                    onChange={(e) => setScheduleForm({ ...scheduleForm, preset: e.target.value })}
                    style={{ background: '#0f131a', color: 'var(--text-primary)' }}
                  >
                    <option value="0 9,18 * * 1-5">Twice Daily — 9 AM & 6 PM Weekdays (Recommended)</option>
                    <option value="0 */6 * * *">Every 6 Hours</option>
                    <option value="0 9 * * *">Once Daily at 9:00 AM</option>
                    <option value="*/30 * * * *">Every 30 Minutes (Testing)</option>
                    <option value="custom">Custom Cron Expression</option>
                  </select>
                </div>

                {/* Custom Cron Input */}
                {scheduleForm.preset === 'custom' && (
                  <div className="input-group">
                    <span className="input-label">Custom Cron Expression (min hour day month day-of-week)</span>
                    <input 
                      type="text"
                      value={scheduleForm.customCron}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, customCron: e.target.value })}
                      placeholder="e.g. 0 9,18 * * 1-5"
                      className="input-field"
                      style={{ fontFamily: 'var(--font-mono)' }}
                    />
                  </div>
                )}

                {/* Max Jobs per Scan Slider */}
                <div className="input-group">
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span className="input-label">Max Jobs Per Scan:</span>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--primary)' }}>{scheduleForm.maxJobs} jobs</span>
                  </div>
                  <input 
                    type="range"
                    min="10"
                    max="100"
                    step="5"
                    value={scheduleForm.maxJobs}
                    onChange={(e) => setScheduleForm({ ...scheduleForm, maxJobs: e.target.value })}
                    style={{ width: '100%', accentColor: 'var(--primary)' }}
                  />
                </div>

                {/* Auto-Apply Toggle & Min Match Score Slider */}
                <div style={{ background: 'var(--bg-surface-elevated)', padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                    <input 
                      type="checkbox" 
                      checked={scheduleForm.autoApply} 
                      onChange={(e) => setScheduleForm({ ...scheduleForm, autoApply: e.target.checked })}
                      style={{ accentColor: 'var(--primary)', width: '16px', height: '16px', cursor: 'pointer' }}
                    />
                    <span>⚡ Auto-Apply to High-Match Jobs (Hands-Free)</span>
                  </label>
                  
                  {scheduleForm.autoApply && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.6rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Minimum Match Cutoff:</span>
                        <strong style={{ color: 'var(--success)' }}>≥ {scheduleForm.minMatchScore}% Match</strong>
                      </div>
                      <input 
                        type="range"
                        min="50"
                        max="90"
                        step="5"
                        value={scheduleForm.minMatchScore}
                        onChange={(e) => setScheduleForm({ ...scheduleForm, minMatchScore: Number(e.target.value) })}
                        style={{ accentColor: 'var(--success)', cursor: 'pointer' }}
                      />
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        Discovered jobs matching your resume ≥ {scheduleForm.minMatchScore}% will automatically trigger Playwright auto-apply!
                      </span>
                    </div>
                  )}
                </div>

                <button 
                  type="submit" 
                  className="btn btn-primary" 
                  disabled={isScheduling}
                  style={{ padding: '0.75rem', marginTop: '0.5rem' }}
                >
                  <Calendar size={16} />
                  {isScheduling ? 'Creating Schedules...' : 'Add Recurring Cron Job'}
                </button>
              </form>
            </div>

            {/* Panel 2: Active Schedules & Rate Limits */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)' }}>
                    <Activity size={16} />
                    Active Recurring Schedules ({schedulesList.length})
                  </h3>
                  {schedulesList.length > 0 && (
                    <button 
                      className="btn" 
                      onClick={handleClearAllSchedules}
                      style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem', background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                    >
                      <Trash2 size={12} /> Clear All
                    </button>
                  )}
                </div>

                {schedulesList.length === 0 ? (
                  <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    No recurring schedules currently active. Create one using the form on the left!
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="schedule-table">
                      <thead>
                        <tr>
                          <th>Job ID / Rule</th>
                          <th>Schedule / Trigger</th>
                          <th>Next Run</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {schedulesList.map((sch) => (
                          <tr key={sch.id}>
                            <td>
                              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{sch.name || sch.id}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{sch.id}</div>
                            </td>
                            <td>
                              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', background: 'var(--bg-surface)', padding: '0.15rem 0.4rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                                {sch.trigger}
                              </span>
                            </td>
                            <td style={{ fontSize: '0.8rem', color: 'var(--secondary)' }}>
                              {sch.next_run ? sch.next_run.replace("T", " ").split(".")[0] : 'Pending'}
                            </td>
                            <td>
                              <button 
                                className="btn"
                                onClick={() => handleRemoveSchedule(sch.id)}
                                style={{ padding: '0.25rem 0.5rem', background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)', fontSize: '0.75rem' }}
                              >
                                <Trash2 size={12} /> Remove
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Rate Limits Breakdown */}
              <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <ShieldCheck size={14} /> Platform Rate Limits & Anti-Bot Protection
                  </h4>
                  <button 
                    className="btn"
                    onClick={handleResetRateLimits}
                    style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}
                  >
                    <RefreshCw size={10} /> Reset Counters
                  </button>
                </div>
                {Object.keys(rateLimitStats).length === 0 ? (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Loading platform rate limits...
                  </div>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
                    {Object.entries(rateLimitStats).map(([plat, stat]) => (
                      <div key={plat} style={{ background: 'var(--bg-surface-elevated)', padding: '0.6rem 0.8rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                        <div style={{ fontWeight: 700, textTransform: 'capitalize', fontSize: '0.8rem' }}>{plat}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                          Hourly: {stat.hourly || '0/5'}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          Daily: {stat.daily || '0/20'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Bottom Panel: Queue Execution Monitor */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)' }}>
                <Activity size={16} />
                Task Queue Execution History ({schedulerTasks.length})
              </h3>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button 
                  className="btn" 
                  onClick={handleClearTaskHistory}
                  style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem', background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                >
                  <Trash2 size={12} /> Clear History
                </button>
                <button className="btn" onClick={fetchSchedulerData} style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}>
                  <RefreshCw size={12} /> Refresh Queue
                </button>
              </div>
            </div>

            {schedulerTasks.length === 0 ? (
              <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                No tasks currently in the queue. Tasks automatically appear when triggered by cron schedules or manual actions.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="schedule-table">
                  <thead>
                    <tr>
                      <th>Task ID</th>
                      <th>Type</th>
                      <th>Priority</th>
                      <th>Status</th>
                      <th>Scheduled At / Created</th>
                      <th>Retries</th>
                      <th>Details / Errors</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schedulerTasks.map((t) => (
                      <tr key={t.id}>
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>#{t.id}</td>
                        <td style={{ textTransform: 'capitalize', fontWeight: 600 }}>{t.task_type.replace('_', ' ')}</td>
                        <td>
                          <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: t.priority === 'urgent' ? 'var(--error)' : 'var(--text-muted)' }}>
                            {t.priority}
                          </span>
                        </td>
                        <td>
                          <span className={`badge-status ${t.status}`}>
                            {t.status}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          {t.scheduled_at ? t.scheduled_at.replace("T", " ").split(".")[0] : t.created_at?.replace("T", " ").split(".")[0]}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{t.retry_count}</td>
                        <td style={{ fontSize: '0.75rem', color: t.error ? 'var(--error)' : 'var(--text-muted)', maxWidth: '250px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {t.error || 'Clean execution'}
                        </td>
                        <td>
                          {(t.status === 'pending' || t.status === 'running') && (
                            <button 
                              className="btn"
                              onClick={() => handleCancelTask(t.id)}
                              style={{ padding: '0.2rem 0.4rem', fontSize: '0.7rem', background: 'rgba(239, 68, 68, 0.1)', color: '#f87171' }}
                            >
                              <XCircle size={10} /> Cancel
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
