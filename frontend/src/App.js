import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Link, useLocation, useNavigate } from "react-router-dom";
// import { useAuth0 } from "@auth0/auth0-react";
import {
  login,
  saveToken,
  getToken,
  logout as logoutUser
} from "./services/authService";

import {
  Layout, Dropdown, Avatar, Space, Typography, Badge, Select, Spin, Card, Button, Tag,
  ConfigProvider, theme, Tooltip, Input, Form, App as AppWrapper
} from "antd";
import { message, setGlobalMessage } from "./utils/message";

import {
  SettingOutlined, UserOutlined, BellOutlined, DownOutlined,
  LockOutlined, SunOutlined, MoonOutlined, DesktopOutlined, CheckOutlined,
  LogoutOutlined, DatabaseOutlined
} from "@ant-design/icons";
import {
  LayoutDashboard, MessageSquare, Database, Code, Tag as TagIcon,
  Cpu, Terminal, GitFork, Users, Shield, Activity, ChevronLeft,
  ChevronRight, ChevronDown, Sliders
} from "lucide-react";
import { useTheme } from "./hooks/useTheme";

// Import all subpages (Architecture removed)
import Overview from "./pages/Overview";
import DataSources from "./pages/DataSources";
import SchemaDiscovery from "./pages/SchemaDiscovery";
import SemanticLayer from "./pages/SemanticLayer";
import PromptStudio from "./pages/PromptStudio";
import AIProviderConfig from "./pages/AIProviderConfig";
import IntentConfig from "./pages/IntentConfig";
import QueryPipelineDebugger from "./pages/QueryPipelineDebugger";
import MonitoringAudit from "./pages/MonitoringAudit";
import UserManagement from "./pages/UserManagement";
import RoleManagement from "./pages/RoleManagement";
import ChatPage from "./pages/ChatPage";
import RBAC from "./pages/RBAC";

import ProfileModal from "./components/ProfileModal";
import PlatformSettingsModal from "./components/PlatformSettingsModal";

const { Header, Content } = Layout;
const { Text, Title, Paragraph } = Typography;
const { Option } = Select;

const API = process.env.REACT_APP_API_BASE_URL || "";



const themeColors = {
  dark: {
    bgLayout: "var(--bg-layout)",
    bgHeader: "var(--bg-header)",
    bgCard: "var(--bg-card)",
    bgCardInner: "var(--bg-card-inner)",
    border: "var(--border-color)",
    borderLight: "var(--border-light)",
    textMain: "var(--text-main)",
    textMuted: "var(--text-muted)",
    textSecondary: "var(--text-secondary)",
    bgSidebar: "var(--bg-sidebar)",
    bgChatSession: "var(--bg-chat-session)",
    bgChatInput: "var(--bg-chat-input)",
    borderChatInput: "var(--border-chat-input)",
    bgSelectedChat: "var(--bg-selected-chat)",
  },
  light: {
    bgLayout: "var(--bg-layout)",
    bgHeader: "var(--bg-header)",
    bgCard: "var(--bg-card)",
    bgCardInner: "var(--bg-card-inner)",
    border: "var(--border-color)",
    borderLight: "var(--border-light)",
    textMain: "var(--text-main)",
    textMuted: "var(--text-muted)",
    textSecondary: "var(--text-secondary)",
    bgSidebar: "var(--bg-sidebar)",
    bgChatSession: "var(--bg-chat-session)",
    bgChatInput: "var(--bg-chat-input)",
    borderChatInput: "var(--border-chat-input)",
    bgSelectedChat: "var(--bg-selected-chat)",
  }
};

const SIDEBAR_SECTIONS = [
  {
    id: "OVERVIEW",
    title: "OVERVIEW",
    icon: LayoutDashboard,
    items: [
      { path: "/", label: "Overview", icon: LayoutDashboard, roles: ["SUPER_ADMIN", "ADMIN"] },
      { path: "/assistant", label: "Launch Assistant", icon: MessageSquare, roles: ["SUPER_ADMIN", "ADMIN", "ANALYST"] }
    ]
  },
  {
    id: "DATA_MANAGEMENT",
    title: "DATA MANAGEMENT",
    icon: Database,
    items: [
      { path: "/connections", label: "Data Sources", icon: Database, roles: ["SUPER_ADMIN"] },
      { path: "/schema", label: "Schema Discovery", icon: Code, roles: ["SUPER_ADMIN", "ADMIN", "ANALYST"] },
      { path: "/semantic", label: "Semantic Layer", icon: TagIcon, roles: ["SUPER_ADMIN", "ADMIN", "ANALYST"] }
    ]
  },
  {
    id: "AI_OPERATIONS",
    title: "AI OPERATIONS",
    icon: Cpu,
    items: [
      { path: "/providers", label: "AI Providers", icon: Cpu, roles: ["SUPER_ADMIN"] },
      { path: "/prompts", label: "Prompt Studio", icon: Terminal, roles: ["SUPER_ADMIN"] },
      { path: "/intents", label: "Intent Configuration", icon: GitFork, roles: ["SUPER_ADMIN"] }
    ]
  },
  {
    id: "USERS_SECURITY",
    title: "USERS & SECURITY",
    icon: Shield,
    items: [
      { path: "/users", label: "User Management", icon: Users, roles: ["SUPER_ADMIN", "ADMIN"] },
      { path: "/roles", label: "Role Management", icon: Shield, roles: ["SUPER_ADMIN"] }
    ]
  },
  {
    id: "ACCESS_CONTROL",
    title: "ACCESS CONTROL",
    icon: Sliders,
    path: "/rbac",
    isSingleLink: true,
    items: [
      { path: "/rbac", label: "ACCESS CONTROL", icon: Sliders, roles: ["SUPER_ADMIN", "ADMIN"] }
    ]
  },
  {
    id: "MONITORING",
    title: "MONITORING",
    icon: Activity,
    items: [
      { path: "/audit", label: "Monitoring & Audit", icon: Activity, roles: ["SUPER_ADMIN", "ADMIN"] }
    ]
  }
];

function MainAppLayout({
  token,
  userInfo,
  onLogout
}) {
  const location = useLocation();
  const navigate = useNavigate();

  const { themeMode, setThemeMode, resolvedTheme } = useTheme();
  const colors = themeColors[resolvedTheme];

  const [profileOpen, setProfileOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [isHovered, setIsHovered] = useState(false);
  const [isPinned, setIsPinned] = useState(false);
  const isExpanded = isPinned || isHovered;
  const [effectiveMatrix, setEffectiveMatrix] = useState(null);

  useEffect(() => {
    if (token) {
      fetch(`${API}/access-control/effective`, {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(res => res.ok ? res.json() : null)
        .then(data => { if (data) setEffectiveMatrix(data); })
        .catch(err => console.error("Failed to load effective access control matrix", err));
    }
  }, [token]);

  const handleLogout = () => {
    onLogout();
  };

  const role = userInfo?.role?.toUpperCase() || "";

  // Helper map path to key
  const pathToKey = {
    "/": "overview",
    "/assistant": "chat",
    "/connections": "connections",
    "/schema": "schema",
    "/semantic": "semantic",
    "/providers": "providers",
    "/prompts": "prompts",
    "/intents": "intents",
    "/users": "users",
    "/roles": "roles",
    "/rbac": "rbac",
    "/audit": "audit"
  };

  // Filter sections by roles AND Page Access V
  const filteredSections = SIDEBAR_SECTIONS.map(section => {
    const items = section.items.filter(item => {
      if (role === "SUPER_ADMIN") return true;
      const pageKey = pathToKey[item.path];
      if (effectiveMatrix && effectiveMatrix.page_access && pageKey && pageKey in effectiveMatrix.page_access) {
        return !!effectiveMatrix.page_access[pageKey]?.v;
      }
      return item.roles.includes(role);
    });
    return { ...section, items };
  }).filter(section => section.items.length > 0);

  const [openSections, setOpenSections] = useState({});


  // Set default active section based on path
  useEffect(() => {
    const currentPath = location.pathname;
    const matchedSection = filteredSections.find(section =>
      section.items.some(item => item.path === currentPath)
    );
    if (matchedSection) {
      setOpenSections(prev => ({ ...prev, [matchedSection.id]: true }));
    }
  }, [location.pathname, role]); // eslint-disable-line

  const handleSectionToggle = (sectionId) => {
    setOpenSections(prev => ({ ...prev, [sectionId]: !prev[sectionId] }));
  };

  const handleCloseSidebar = () => {
    setIsPinned(false);
    setIsHovered(false);
  };

  // Keyboard navigation & accessibility for sidebar: escape key closes it
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && isExpanded) {
        handleCloseSidebar();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isExpanded]);

  const userDropdownItems = [
    { key: "profile", label: "My Profile", icon: <UserOutlined />, onClick: () => setProfileOpen(true) },
    {
      key: "theme",
      label: "Theme Mode",
      icon: resolvedTheme === "dark" ? <MoonOutlined /> : <SunOutlined />,
      children: [
        {
          key: "theme-light",
          label: (
            <Space style={{ display: "flex", justifyContent: "space-between", width: "100%", minWidth: "120px" }}>
              <span>Light Mode</span>
              {themeMode === "light" && <CheckOutlined style={{ color: "#4f46e5" }} />}
            </Space>
          ),
          icon: <SunOutlined />,
          onClick: () => setThemeMode("light")
        },
        {
          key: "theme-dark",
          label: (
            <Space style={{ display: "flex", justifyContent: "space-between", width: "100%", minWidth: "120px" }}>
              <span>Dark Mode</span>
              {themeMode === "dark" && <CheckOutlined style={{ color: "#4f46e5" }} />}
            </Space>
          ),
          icon: <MoonOutlined />,
          onClick: () => setThemeMode("dark")
        },
        {
          key: "theme-system",
          label: (
            <Space style={{ display: "flex", justifyContent: "space-between", width: "100%", minWidth: "120px" }}>
              <span>System</span>
              {themeMode === "system" && <CheckOutlined style={{ color: "#4f46e5" }} />}
            </Space>
          ),
          icon: <DesktopOutlined />,
          onClick: () => setThemeMode("system")
        }
      ]
    },
    { type: "divider" },
    { key: "logout", label: "Logout", icon: <LogoutOutlined />, danger: true, onClick: handleLogout }
  ];

  return (
    <Layout className="app-root-layout">
      {/* Sidebar Backdrop Overlay on Mobile */}
      {isExpanded && (
        <div 
          className="sidebar-backdrop" 
          onClick={handleCloseSidebar}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Navigation */}
      <div
        className={`custom-sidebar ${isExpanded ? "expanded" : ""}`}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Sidebar Header */}
        <div className="sidebar-logo-container">
          <div className="sidebar-logo-icon">
            <LayoutDashboard size={22} />
          </div>
          <div className="sidebar-logo-text">
            <span className="sidebar-logo-title">RR Convo AI Bot</span>
            <span className="sidebar-logo-subtitle">Analytics Platform</span>
          </div>
        </div>

        {/* Sidebar Content */}
        <div className="sidebar-content">
          {isExpanded ? (
            filteredSections.map(section => {
              if (section.isSingleLink && section.path) {
                const isActive = location.pathname === section.path;
                const Icon = section.icon;
                return (
                  <div key={section.id} className="sidebar-section">
                    <Link
                      to={section.path}
                      className={`sidebar-item ${isActive ? 'active' : ''}`}
                      style={{ paddingLeft: "10px", margin: "2px 0" }}
                    >
                      <div className="sidebar-item-icon-wrapper">
                        <Icon size={18} />
                      </div>
                      <span className="sidebar-item-label" style={{ fontWeight: 600, fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                        {section.title}
                      </span>
                    </Link>
                  </div>
                );
              }
              const isOpen = !!openSections[section.id];
              return (
                <div key={section.id} className="sidebar-section">
                  <button 
                    type="button"
                    className="sidebar-section-header" 
                    onClick={() => handleSectionToggle(section.id)}
                    aria-expanded={isOpen}
                    aria-label={`Toggle ${section.title} section`}
                    style={{ border: "none", background: "transparent", width: "100%", fontFamily: "inherit", outline: "none" }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <section.icon size={14} style={{ color: "var(--text-muted)" }} />
                      <span>{section.title}</span>
                    </div>
                    <ChevronDown size={12} className={`chevron-icon ${isOpen ? 'open' : ''}`} />
                  </button>
                  <div className={`sidebar-section-items ${isOpen ? 'open' : 'collapsed'}`}>
                    {section.items.map(item => {
                      const isActive = location.pathname === item.path;
                      const Icon = item.icon;
                      return (
                        <Link
                          key={item.path}
                          to={item.path}
                          className={`sidebar-item ${isActive ? 'active' : ''}`}
                        >
                          <div className="sidebar-item-icon-wrapper">
                            <Icon size={20} />
                          </div>
                          <span className="sidebar-item-label">{item.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              );
            })
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px", alignItems: "center", width: "100%" }}>
              {filteredSections.map(section => {
                const isGroupActive = section.items.some(item => location.pathname === item.path);
                const GroupIcon = section.icon;
                return (
                  <Tooltip key={section.id} title={section.title} placement="right">
                    <div
                      className={`sidebar-group-collapsed-icon ${isGroupActive ? 'active' : ''}`}
                      onClick={() => {
                        if (section.isSingleLink && section.path) {
                          navigate(section.path);
                        } else {
                          setIsPinned(true);
                          setOpenSections(prev => ({ ...prev, [section.id]: true }));
                        }
                      }}
                    >
                      <GroupIcon size={22} />
                    </div>
                  </Tooltip>
                );
              })}
            </div>
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
            <Dropdown menu={{ items: userDropdownItems }} trigger={["click"]} placement="topRight">
              <div className="sidebar-profile" style={{ width: "100%" }}>
                <Avatar style={{ backgroundColor: "#6366f1", width: 36, height: 36 }} icon={<UserOutlined />} />
                {isExpanded && (
                  <div className="sidebar-profile-info">
                    <span className="sidebar-profile-name">{userInfo?.full_name || "Aathiganapathi K"}</span>
                    <span className="sidebar-profile-role">{userInfo?.role || "SUPER_ADMIN"}</span>
                  </div>
                )}
              </div>
            </Dropdown>
          </div>
        </div>
      </div>

      {/* Main Body */}
      <Layout className="app-main-content-layout">
        {/* Top Header */}
        <Header
          style={{
            background: "var(--bg-header)",
            borderBottom: "1px solid var(--border-color)",
            padding: "0 24px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            height: "64px",
            position: "sticky",
            top: 0,
            zIndex: 99
          }}
        >
          {/* Company tenant display */}
          <Space size="middle">
            <Button
              type="text"
              className="mobile-sidebar-toggle"
              icon={isPinned ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
              onClick={() => setIsPinned(!isPinned)}
              style={{ display: "none" }}
            />
            <span style={{ color: "var(--text-main)", fontWeight: 600 }}>
              {userInfo?.company_name || userInfo?.company || "Ramraj Company"}
            </span>
            {userInfo?.role && (
              <Tag color={(userInfo.role.toUpperCase() === "ADMIN" || userInfo.role.toUpperCase() === "SUPER_ADMIN") ? "volcano" : "blue"} bordered={false}>
                {userInfo.role.toUpperCase()}
              </Tag>
            )}
          </Space>

          {/* User & Notifications */}
          <Space size="large">
            <Badge count={3} size="small" style={{ backgroundColor: "#6366f1" }}>
              <Button type="text" icon={<BellOutlined style={{ color: "var(--text-main)", fontSize: "18px" }} />} />
            </Badge>
          </Space>
        </Header>

        {/* Content Router Area */}
        <Content style={{ padding: "24px", background: "var(--bg-layout)", minHeight: "calc(100vh - 64px)" }}>
          {(() => {
            const isAllowed = (pageKey, legacyRoles) => {
              if (role === "SUPER_ADMIN") return true;
              if (effectiveMatrix && effectiveMatrix.page_access && pageKey) {
                return !!effectiveMatrix.page_access[pageKey]?.v;
              }
              return legacyRoles.includes(role);
            };

            const DeniedView = () => (
              <Card style={{ textAlign: "center", marginTop: 40, padding: 30 }}>
                <Title level={3} style={{ color: "#ef4444" }}>403 - Access Denied</Title>
                <Paragraph style={{ color: "var(--text-secondary)" }}>
                  You do not have View (V) permission to access this page. Contact your system administrator to update your Access Control Matrix.
                </Paragraph>
                <Button type="primary" onClick={() => navigate("/assistant")}>
                  Return to Chat Assistant
                </Button>
              </Card>
            );

            return (
              <Routes>
                <Route path="/assistant" element={isAllowed("chat", ["SUPER_ADMIN", "ADMIN", "ANALYST"]) ? <ChatPage API={API} token={token} userInfo={userInfo} /> : <DeniedView />} />
                <Route path="/schema" element={isAllowed("schema", ["SUPER_ADMIN", "ADMIN", "ANALYST"]) ? <SchemaDiscovery API={API} token={token} userInfo={userInfo} /> : <DeniedView />} />
                <Route path="/semantic" element={isAllowed("semantic", ["SUPER_ADMIN", "ADMIN", "ANALYST"]) ? <SemanticLayer API={API} token={token} userInfo={userInfo} /> : <DeniedView />} />

                <Route path="/" element={isAllowed("overview", ["SUPER_ADMIN", "ADMIN"]) ? <Overview API={API} token={token} /> : <DeniedView />} />
                <Route path="/audit" element={isAllowed("audit", ["SUPER_ADMIN", "ADMIN"]) ? <MonitoringAudit API={API} token={token} /> : <DeniedView />} />
                <Route path="/users" element={isAllowed("users", ["SUPER_ADMIN", "ADMIN"]) ? <UserManagement API={API} token={token} userInfo={userInfo} /> : <DeniedView />} />

                <Route path="/connections" element={isAllowed("connections", ["SUPER_ADMIN"]) ? <DataSources API={API} token={token} /> : <DeniedView />} />
                <Route path="/prompts" element={isAllowed("prompts", ["SUPER_ADMIN"]) ? <PromptStudio /> : <DeniedView />} />
                <Route path="/providers" element={isAllowed("providers", ["SUPER_ADMIN"]) ? <AIProviderConfig API={API} token={token} /> : <DeniedView />} />
                <Route path="/intents" element={isAllowed("intents", ["SUPER_ADMIN"]) ? <IntentConfig /> : <DeniedView />} />
                <Route path="/pipeline" element={isAllowed("pipeline", ["SUPER_ADMIN"]) ? <QueryPipelineDebugger /> : <DeniedView />} />
                <Route path="/roles" element={isAllowed("roles", ["SUPER_ADMIN"]) ? <RoleManagement API={API} token={token} /> : <DeniedView />} />
                <Route path="/rbac" element={isAllowed("rbac", ["SUPER_ADMIN", "ADMIN"]) ? <RBAC API={API} token={token} userInfo={userInfo} /> : <DeniedView />} />
              </Routes>
            );
          })()}
        </Content>
      </Layout>

      {/* Modals */}
      <ProfileModal visible={profileOpen} onClose={() => setProfileOpen(false)} userInfo={userInfo} />
    </Layout>
  );
}

const darkThemeTokens = {
  colorPrimary: "#4f46e5",
  colorBgLayout: "#030712",
  colorBgContainer: "#111827",
  colorBgElevated: "#1f2937",
  colorText: "#ffffff",
  colorTextSecondary: "#d1d5db",
  colorBorder: "#1f2937",
  colorSuccess: "#10b981",
  colorWarning: "#f59e0b",
  colorError: "#ef4444",
  borderRadius: 8,
  fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
};

const lightThemeTokens = {
  colorPrimary: "#4f46e5",
  colorBgLayout: "#f3f4f6",
  colorBgContainer: "#ffffff",
  colorBgElevated: "#ffffff",
  colorText: "#111827",
  colorTextSecondary: "#374151",
  colorBorder: "#e5e7eb",
  colorSuccess: "#10b981",
  colorWarning: "#f59e0b",
  colorError: "#ef4444",
  borderRadius: 8,
  fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
};

function InnerApp() {
  const { resolvedTheme } = useTheme();
  const { message: antdMessage } = AppWrapper.useApp();

  useEffect(() => {
    setGlobalMessage(antdMessage);
  }, [antdMessage]);

  const [token, setToken] = useState(getToken() || "");
  const [isAuthenticated, setIsAuthenticated] = useState(!!getToken());
  const [authLoading, setAuthLoading] = useState(true);

  const [userInfo, setUserInfo] = useState(null);
  const [backendStatus, setBackendStatus] = useState("idle");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginForm] = Form.useForm();

  const handleLogin = async (values) => {
    try {
      setLoginLoading(true);

      const result = await login(
        values.email,
        values.password
      );

      saveToken(result.access_token);

      setToken(result.access_token);
      setIsAuthenticated(true);

      await fetchUserInfo(result.access_token);

      message.success("Login successful");

    } catch (err) {
      message.error(err.message || "Login failed");
    } finally {
      setLoginLoading(false);
    }
  };

  const fetchUserInfo = async (authToken) => {
    setBackendStatus("loading");
    try {
      const activeToken = authToken || token;
      if (!activeToken) return;

      const res = await fetch(`${API}/profile`, {
        headers: { Authorization: `Bearer ${activeToken}` }
      });

      if (res.status === 401) {
        setBackendStatus("error");
        return;
      }


      if (res.status === 403) {
        const body = await res.json().catch(() => ({}));
        const detail = body.detail || "";
        if (detail.toLowerCase().includes("inactive")) {
          setBackendStatus("inactive");
        } else {
          setBackendStatus("not_provisioned");
        }
        return;
      }

      if (!res.ok) {
        setBackendStatus("error");
        return;
      }

      const data = await res.json();
      setUserInfo(data);
      setBackendStatus("provisioned");
    } catch (e) {
      console.error("Failed to load user profile", e);
      setBackendStatus("error");
    }
  };

  // useEffect(() => {
  //   const initAuth = async () => {
  //     if (isAuthenticated) {

  //       try {
  //         const auth0Token = await getAccessTokenSilently();
  //         setToken(auth0Token);
  //         window.appState = { token: auth0Token, userInfo: null }; // Set globally for subcomponents
  //         await fetchUserInfo(auth0Token);
  //       } catch (err) {
  //         console.error("Auth0 token error:", err);
  //         setBackendStatus("error");
  //       }
  //     }
  //   };
  //   initAuth();
  // }, [isAuthenticated, getAccessTokenSilently]); // eslint-disable-line

  useEffect(() => {

    const existingToken = getToken();

    if (!existingToken) {
      setAuthLoading(false);
      return;
    }

    setToken(existingToken);

    fetchUserInfo(existingToken)
      .finally(() => {
        setAuthLoading(false);
        setIsAuthenticated(true);
      });

  }, []);

  useEffect(() => {
    if (userInfo) {
      window.appState = { token, userInfo };
    }
  }, [userInfo, token]);

  if (authLoading || (isAuthenticated && backendStatus === "loading") || (isAuthenticated && backendStatus === "idle")) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-layout)" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (backendStatus === "not_provisioned" || backendStatus === "inactive") {
    const msg = backendStatus === "inactive"
      ? "Your account is inactive. Contact your administrator."
      : "Your account is not provisioned. Contact your administrator to request access.";
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-layout)", padding: "20px" }}>
        <Card style={{ width: "440px", background: "var(--bg-card)", border: "1px solid var(--border-color)", textAlign: "center" }} styles={{ body: { padding: "40px" } }}>
          <Avatar size={64} icon={<LockOutlined />} style={{ backgroundColor: "#ef4444", marginBottom: "20px" }} />
          <Title level={3} style={{ color: "var(--text-main)" }}>Access Denied</Title>
          <Text style={{ fontSize: "15px", display: "block", marginBottom: "24px", color: "var(--text-muted)" }}>{msg}</Text>
          <Tag color="red">MFA · RBAC Policy enforced</Tag>
        </Card>
      </div>
    );
  }

  const handleLogout = () => {
    logoutUser();

    setToken("");
    setUserInfo(null);
    setIsAuthenticated(false);
    setBackendStatus("idle");

    window.appState = null;
  };


  return (
    <div className={resolvedTheme === "dark" ? "dark-theme" : "light-theme"} style={{ minHeight: "100vh" }}>
      {!isAuthenticated || backendStatus !== "provisioned" ? (
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            background: "linear-gradient(135deg, var(--bg-layout) 0%, var(--bg-header) 50%, #1e1b4b 100%)",
            padding: "20px"
          }}
        >
          <Card
            style={{
              width: "420px",
              borderRadius: "16px",
              border: "1px solid var(--border-color)",
              background: "var(--bg-card)"
            }}
            styles={{ body: { padding: "40px 30px" } }}
          >
              <div style={{ textAlign: "center", marginBottom: "30px" }}>
                <Avatar
                  size={54}
                  icon={<DatabaseOutlined />}
                  style={{ backgroundColor: "#4f46e5", marginBottom: "12px" }}
                />
                <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
                  RR-AI BOT LOGIN
                </Title>
                <Text style={{ color: "var(--text-muted)", fontSize: "14px" }}>
                  Retail Executive Business Intelligence & Analytics
                </Text>
              </div>

              {/* <Button
                type="primary"
                size="large"
                block
                icon={<LockOutlined />}
                disabled
                style={{
                  height: "48px",
                  fontWeight: 600,
                  borderRadius: "8px",
                  background: "#4f46e5",
                  fontSize: "15px"
                }}
              >
                Login Screen Coming Next...
              </Button> */}

              <Form
                form={loginForm}
                layout="vertical"
                onFinish={handleLogin}
              >

                <Form.Item
                  label="Official Email"
                  name="email"
                  rules={[
                    {
                      required: true,
                      message: "Please enter your email"
                    }
                  ]}
                >
                  <Input
                    placeholder="admin@company.com"
                    size="large"
                  />
                </Form.Item>

                <Form.Item
                  label="Password"
                  name="password"
                  rules={[
                    {
                      required: true,
                      message: "Please enter your password"
                    }
                  ]}
                >
                  <Input.Password
                    size="large"
                    placeholder="Password"
                  />
                </Form.Item>

                <Button
                  htmlType="submit"
                  type="primary"
                  block
                  size="large"
                  loading={loginLoading}
                  icon={<LockOutlined />}
                  style={{
                    marginTop: 8,
                    height: "48px",
                    fontWeight: 600,
                    borderRadius: "8px",
                    background: "#4f46e5",
                    fontSize: "15px"
                  }}
                >
                  Sign In
                </Button>

              </Form>

              <div style={{ textAlign: "center", marginTop: "24px" }}>
                <Tag color="blue">
                  JWT · RBAC · RLS · CLS Protected
                </Tag>
              </div>
            </Card>
          </div>
        ) : (
          <BrowserRouter>
            <MainAppLayout
              token={token}
              userInfo={userInfo}
              onLogout={handleLogout}
            />
          </BrowserRouter>
        )}
    </div>
  );
}

export default function App() {
  const { resolvedTheme } = useTheme();

  return (
    <ConfigProvider
      theme={{
        algorithm: resolvedTheme === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: resolvedTheme === "dark" ? darkThemeTokens : lightThemeTokens
      }}
    >
      <AppWrapper>
        <InnerApp />
      </AppWrapper>
    </ConfigProvider>
  );
}
