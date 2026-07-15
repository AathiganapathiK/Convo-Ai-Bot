import React, { useState, useEffect, useRef } from "react";
import { 
  Layout, Input, Button, Card, Space, Avatar, Tag, Typography, 
  Collapse, Table, Spin, Alert, Modal, Statistic, Row, Col, 
  List, Popconfirm, Tooltip, message, ConfigProvider 
} from "antd";
import { 
  SendOutlined, PlusOutlined, MessageOutlined, DatabaseOutlined, 
  FileExcelOutlined, LockOutlined, UserOutlined, ArrowRightOutlined, 
  DeleteOutlined, EditOutlined, CopyOutlined, CodeOutlined, 
  CheckCircleOutlined, SmileOutlined, LoadingOutlined, AlertOutlined, 
  AudioOutlined, AudioMutedOutlined, BarChartOutlined, BulbOutlined, 
  RocketOutlined, UpOutlined, DownOutlined, DownloadOutlined 
} from "@ant-design/icons";
import KPICards from "../components/charts/KPICards";
import ChartTabs from "../components/charts/ChartTabs";

const { Sider, Content } = Layout;
const { Text, Title, Paragraph } = Typography;
const { Panel } = Collapse;

const parseBusinessSummary = (text) => {
  if (!text) return { keyFindings: "", executiveSummary: "", recommendation: "" };

  let keyFindings = "";
  let executiveSummary = "";
  let recommendation = "";

  const lines = text.split("\n");
  let currentSection = "";

  lines.forEach(line => {
    const trimmed = line.trim();
    if (!trimmed) return;

    // Clean line for header detection
    const cleanLine = trimmed.replace(/[*#:_]/g, "").trim().toLowerCase();

    if (
      cleanLine === "key findings" ||
      cleanLine === "trend analysis" ||
      cleanLine === "top performer insights" ||
      cleanLine === "dataset summary"
    ) {
      currentSection = "keyFindings";
      return;
    } else if (cleanLine === "executive summary") {
      currentSection = "executiveSummary";
      return;
    } else if (
      cleanLine === "recommendation" ||
      cleanLine === "business impact"
    ) {
      currentSection = "recommendation";
      return;
    }

    // Append to current section
    if (currentSection === "keyFindings") {
      keyFindings += (keyFindings ? "\n" : "") + line;
    } else if (currentSection === "executiveSummary") {
      executiveSummary += (executiveSummary ? "\n" : "") + line;
    } else if (currentSection === "recommendation") {
      recommendation += (recommendation ? "\n" : "") + line;
    } else {
      executiveSummary += (executiveSummary ? "\n" : "") + line;
    }
  });

  return {
    keyFindings: keyFindings.trim(),
    executiveSummary: executiveSummary.trim(),
    recommendation: recommendation.trim()
  };
};

const copyTextToClipboard = (text, typeName = "Text") => {
  if (!text) return;
  navigator.clipboard.writeText(text);
  message.success(`${typeName} copied to clipboard!`);
};

const formatMessageTime = (timestamp) => {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", hour12: true });
};

const downloadChartAsSVG = (chartTitle) => {
  const svgElement = document.querySelector(".recharts-responsive-container svg");
  if (!svgElement) {
    message.warning("No active chart visualization visible to download.");
    return;
  }
  try {
    const serializer = new XMLSerializer();
    let source = serializer.serializeToString(svgElement);
    if (!source.match(/^<svg[^>]+xmlns="http:\/\/www\.w3\.org\/2000\/svg"/)) {
      source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    if (!source.match(/^<svg[^>]+xmlns:xlink="http:\/\/www\.w3\.org\/1999\/xlink"/)) {
      source = source.replace(/^<svg/, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
    }
    const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(source);
    const downloadLink = document.createElement("a");
    downloadLink.href = url;
    downloadLink.download = `${chartTitle || "retail_chart"}.svg`;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    message.success("Chart downloaded as SVG!");
  } catch (err) {
    console.error(err);
    message.error("Failed to download chart.");
  }
};

const WorkspaceSection = ({ title, icon, children, isOpen, onToggle, extra }) => {
  return (
    <Card 
      bordered={false}
      style={{
        background: "var(--bg-card-inner)",
        border: "1px solid var(--border-color)",
        borderRadius: "8px",
        marginBottom: "8px",
        overflow: "hidden"
      }}
      bodyStyle={{ padding: "0px" }}
    >
      <div 
        onClick={onToggle}
        style={{
          padding: "12px 16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
          background: "var(--bg-card)",
          borderBottom: isOpen ? "1px solid var(--border-color)" : "none"
        }}
      >
        <Space>
          {icon}
          <span style={{ fontWeight: 700, fontSize: "13.5px", color: "var(--text-main)", letterSpacing: "0.2px" }}>{title}</span>
        </Space>
        <Space onClick={(e) => e.stopPropagation()}>
          {extra}
          <Button 
            type="text" 
            size="small" 
            icon={isOpen ? <UpOutlined style={{ color: "var(--text-muted)" }} /> : <DownOutlined style={{ color: "var(--text-muted)" }} />} 
            onClick={onToggle}
          />
        </Space>
      </div>
      {isOpen && (
        <div className="fade-in-message" style={{ padding: "16px" }}>
          {children}
        </div>
      )}
    </Card>
  );
};

const AnalyticsWorkspace = ({ msg, userInfo, downloadExcel, askQuestion, tableColumns, formatMessageTime }) => {
  const [expandAll, setExpandAll] = useState(true);
  const [secStates, setSecStates] = useState({
    summary: true,
    insights: true,
    recommendations: true,
    followup: true,
    kpis: true,
    charts: true,
    table: true,
    sql: false
  });

  const handleToggleAll = () => {
    const nextState = !expandAll;
    setExpandAll(nextState);
    setSecStates({
      summary: nextState,
      insights: nextState,
      recommendations: nextState,
      followup: nextState,
      kpis: nextState,
      charts: nextState,
      table: nextState,
      sql: nextState
    });
  };

  const toggleSection = (key) => {
    setSecStates(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const summaryParts = parseBusinessSummary(msg.business_summary);

  const hasKPIs = msg.kpis && 
                  (Array.isArray(msg.kpis) 
                    ? msg.kpis.length > 0 
                    : (typeof msg.kpis === 'object' && Object.keys(msg.kpis).length > 0 && Object.values(msg.kpis).some(val => val !== null && val !== undefined && val !== "")));

  return (
    <Card 
      bordered={false} 
      style={{ 
        background: "var(--bg-card)", 
        border: "1px solid var(--border-color)", 
        borderTop: "4px solid #6366f1",
        borderRadius: "14px",
        boxShadow: "0 6px 20px rgba(0, 0, 0, 0.05)",
        width: "100%"
      }}
      bodyStyle={{ padding: "20px" }}
    >
      <div style={{ 
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "center", 
        borderBottom: "1px solid var(--border-color)", 
        paddingBottom: "16px",
        marginBottom: "20px" 
      }}>
        <Space size="middle">
          <Avatar style={{ backgroundColor: "#6366f1" }} icon={<SmileOutlined />} />
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontWeight: 800, fontSize: "16px", color: "var(--text-main)" }}>AI Intelligence Workspace</span>
              <Tag color="indigo" style={{ fontWeight: 600, borderRadius: "4px" }}>Active Report</Tag>
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
              Generated • {formatMessageTime(msg.timestamp)}
            </div>
          </div>
        </Space>
        
        <Space size="small">
          <Tooltip title={expandAll ? "Collapse All Sections" : "Expand All Sections"}>
            <Button 
              size="small" 
              icon={expandAll ? <UpOutlined /> : <DownOutlined />} 
              onClick={handleToggleAll}
              style={{ fontSize: "12px" }}
            >
              {expandAll ? "Collapse All" : "Expand All"}
            </Button>
          </Tooltip>
          <Tooltip title="Copy Report Summary">
            <Button 
              size="small" 
              icon={<CopyOutlined />} 
              onClick={() => copyTextToClipboard(msg.business_summary || msg.content, "Summary")}
            />
          </Tooltip>
          {msg.sql_query && (
            <Tooltip title="Copy Generated SQL">
              <Button 
                size="small" 
                icon={<CodeOutlined />} 
                onClick={() => copyTextToClipboard(msg.sql_query, "SQL Query")}
              />
            </Tooltip>
          )}
          <Button
            type="primary"
            size="small"
            icon={<FileExcelOutlined />}
            onClick={() => downloadExcel(msg.content, msg.business_summary, msg.data)}
            style={{ backgroundColor: "#10b981", borderColor: "#10b981", fontWeight: 600 }}
          >
            Export Excel
          </Button>
        </Space>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        
        {summaryParts.executiveSummary && (
          <WorkspaceSection 
            title="Executive Summary" 
            icon={<BulbOutlined style={{ color: "#f59e0b", fontSize: "15px" }} />}
            isOpen={secStates.summary}
            onToggle={() => toggleSection("summary")}
          >
            <div style={{ color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.6", whiteSpace: "pre-line" }}>
              {summaryParts.executiveSummary}
            </div>
          </WorkspaceSection>
        )}

        {summaryParts.keyFindings && (
          <WorkspaceSection 
            title="Key Insights" 
            icon={<BarChartOutlined style={{ color: "#6366f1", fontSize: "15px" }} />}
            isOpen={secStates.insights}
            onToggle={() => toggleSection("insights")}
          >
            <div style={{ color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.6", whiteSpace: "pre-line" }}>
              {summaryParts.keyFindings}
            </div>
          </WorkspaceSection>
        )}

        {summaryParts.recommendation && (
          <WorkspaceSection 
            title="Recommendations" 
            icon={<RocketOutlined style={{ color: "#10b981", fontSize: "15px" }} />}
            isOpen={secStates.recommendations}
            onToggle={() => toggleSection("recommendations")}
          >
            <div style={{ color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.6", whiteSpace: "pre-line" }}>
              {summaryParts.recommendation}
            </div>
          </WorkspaceSection>
        )}

        {hasKPIs && (
          <WorkspaceSection 
            title="KPI Metrics" 
            icon={<CheckCircleOutlined style={{ color: "#10b981", fontSize: "15px" }} />}
            isOpen={secStates.kpis}
            onToggle={() => toggleSection("kpis")}
          >
            <KPICards kpis={msg.kpis} />
          </WorkspaceSection>
        )}

        {msg.chart && (
          <WorkspaceSection 
            title={msg.chart.title || "Visual Analysis"} 
            icon={<BarChartOutlined style={{ color: "#6366f1", fontSize: "15px" }} />}
            isOpen={secStates.charts}
            onToggle={() => toggleSection("charts")}
            extra={
              <Button 
                size="small" 
                icon={<DownloadOutlined />} 
                onClick={() => downloadChartAsSVG(msg.chart.title)}
              >
                Download Chart
              </Button>
            }
          >
            <div style={{ marginBottom: "12px", color: "var(--text-muted)", fontSize: "13px" }}>
              {msg.chart.insight}
            </div>
            <ChartTabs chart={msg.chart} data={msg.chart_data || msg.data} />
          </WorkspaceSection>
        )}

        {msg.data && (
          <WorkspaceSection 
            title={`View Dataset (${msg.data.length} Rows)`}
            icon={<DatabaseOutlined style={{ color: "#4f46e5", fontSize: "15px" }} />}
            isOpen={secStates.table}
            onToggle={() => toggleSection("table")}
          >
            <div className="table-metadata-header">
              <DatabaseOutlined style={{ color: "#6366f1" }} />
              <span>{msg.data.length} Records</span>
              <span style={{ color: "var(--border-light)" }}>|</span>
              <span>{Object.keys(msg.data[0] || {}).length} Columns</span>
            </div>
            <Table 
              dataSource={msg.data.map((row, i) => ({ ...row, key: i }))} 
              columns={tableColumns(msg.data)} 
              pagination={{ 
                pageSize: 5,
                showSizeChanger: false,
                size: "small",
              }} 
              size="small" 
              scroll={{ x: "max-content" }}
              sticky
              style={{ background: "var(--bg-card)" }} 
              className="dark-table" 
            />
          </WorkspaceSection>
        )}

        {(userInfo?.role === "ADMIN" || userInfo?.role === "SUPER_ADMIN") && msg.sql_query && (
          <WorkspaceSection 
            title="Generated SQL Query" 
            icon={<CodeOutlined style={{ color: "#6366f1", fontSize: "15px" }} />}
            isOpen={secStates.sql}
            onToggle={() => toggleSection("sql")}
            extra={
              <Button 
                size="small" 
                icon={<CopyOutlined />} 
                onClick={() => { navigator.clipboard.writeText(msg.sql_query); message.success("Copied!"); }}
              >
                Copy
              </Button>
            }
          >
            <pre style={{ 
              background: "var(--bg-layout)", 
              color: "var(--text-active)", 
              padding: "14px", 
              borderRadius: "6px", 
              overflowX: "auto", 
              fontFamily: "monospace", 
              margin: 0 
            }}>
              {msg.sql_query}
            </pre>
          </WorkspaceSection>
        )}

        {msg.followup_questions?.length > 0 && (
          <WorkspaceSection 
            title="Recommended Next Questions" 
            icon={<ArrowRightOutlined style={{ color: "#6366f1", fontSize: "14px" }} />}
            isOpen={secStates.followup}
            onToggle={() => toggleSection("followup")}
          >
            <div className="suggestion-chips-container" style={{ marginTop: "0px" }}>
              {msg.followup_questions.map((question, index) => (
                <button
                  key={index}
                  className="suggestion-chip"
                  onClick={() => askQuestion(question)}
                >
                  <ArrowRightOutlined style={{ color: "#6366f1", fontSize: "11px", flexShrink: 0 }} />
                  <span>{question}</span>
                </button>
              ))}
            </div>
          </WorkspaceSection>
        )}

      </div>
    </Card>
  );
};

export default function ChatPage({ API, token, userInfo }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [historyChats, setHistoryChats] = useState([]);
  const [renameChatId, setRenameChatId] = useState(null);
  const [renameChatName, setRenameChatName] = useState("");
  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  useEffect(() => {
    if (token) {
      loadChatSessions(true);
    }
  }, [token]); // eslint-disable-line

  useEffect(() => {
    if (selectedSessionId) {
      localStorage.setItem("selectedSessionId", selectedSessionId);
    } else {
      localStorage.removeItem("selectedSessionId");
    }
  }, [selectedSessionId]);

  const generateChartMetadata = (question, rows) => {
    if (!rows || !rows.length) return null;
    const columns = Object.keys(rows[0]);
    if (columns.length < 2) return null;

    const dateColumns = [];
    const numericColumns = [];
    const categoryColumns = [];

    columns.forEach(col => {
      const sample = rows[0][col];
      if (sample === null || sample === undefined) return;
      const colLower = col.toLowerCase();

      if (colLower.includes("date") || colLower.includes("month") || colLower.includes("year")) {
        dateColumns.push(col);
      } else if (typeof sample === "number" || (typeof sample === "string" && !isNaN(Number(sample)) && sample.trim() !== "")) {
        numericColumns.push(col);
      } else {
        categoryColumns.push(col);
      }
    });

    if (dateColumns.length && numericColumns.length) {
      return {
        recommended_view: "line",
        available_views: ["table", "line", "bar"],
        x_axis: dateColumns[0],
        y_axis: numericColumns[0],
        measures: numericColumns,
        title: `${numericColumns[0]} Trend`
      };
    }

    if (categoryColumns.length === 1 && rows.length > 1 && rows.length <= 8 && numericColumns.length) {
      return {
        recommended_view: "pie",
        available_views: ["table", "pie", "bar"],
        x_axis: categoryColumns[0],
        y_axis: numericColumns[0],
        title: `${numericColumns[0]} Distribution`
      };
    }

    if (categoryColumns.length && numericColumns.length) {
      const uniqueCategories = new Set(rows.map(row => String(row[categoryColumns[0]]))).size;
      return {
        recommended_view: "bar",
        available_views: ["table", "bar", ...(uniqueCategories <= 15 ? ["pie"] : [])],
        x_axis: categoryColumns[0],
        y_axis: numericColumns[0],
        layout: uniqueCategories >= 6 ? "horizontal" : "vertical",
        title: `${numericColumns[0]} by ${categoryColumns[0]}`
      };
    }

    return null;
  };

  const loadChatSessions = async (shouldLoadMessages = false) => {
    try {
      const response = await fetch(`${API}/chat-sessions`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await response.json();

      if (Array.isArray(data)) {
        setHistoryChats(data);
        if (shouldLoadMessages) {
          const savedSessionId = localStorage.getItem("selectedSessionId");
          if (savedSessionId) {
            const parsedId = Number(savedSessionId);
            if (data.some(session => session.id === parsedId)) {
              loadSessionMessages(parsedId);
            } else {
              localStorage.removeItem("selectedSessionId");
            }
          }
        }
      } else {
        setHistoryChats([]);
      }
    } catch (error) {
      console.error(error);
    }
  };

  const loadSessionMessages = async (sessionId) => {
    try {
      const response = await fetch(`${API}/chat-sessions/${sessionId}/messages`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await response.json();
      console.log(
        "API RESPONSE:",
        data
      );
      const formattedMessages = [];

      data.forEach(msg => {
        if (msg.role === "USER") {
          formattedMessages.push({
            id: msg.id || Date.now().toString(),
            role: "user",
            content: msg.message_text
          });
        } else {
          let parsedData = null;
          if (msg.result_data) {
            try {
              parsedData = JSON.parse(msg.result_data);
              if (Array.isArray(parsedData)) {
                parsedData = parsedData.map(row => {
                  const newRow = {};
                  let emptyColIdx = 1;
                  Object.keys(row).forEach(key => {
                    let newKey = key;
                    if (key === "") {
                      newKey = emptyColIdx === 1 ? "Value" : `Value_${emptyColIdx}`;
                      emptyColIdx++;
                    }
                    const val = row[key];
                    if (typeof val === "string" && val.trim() !== "" && !isNaN(Number(val))) {
                      newRow[newKey] = Number(val);
                    } else {
                      newRow[newKey] = val;
                    }
                  });
                  return newRow;
                });
              }
            } catch (e) {
              console.error("Error parsing result_data", e);
            }
          }
          const chartMetadata = msg.chart || (parsedData ? generateChartMetadata(msg.message_text, parsedData) : null);
          
          let kpis = null;
          if (parsedData && parsedData.length === 1) {
            const firstRow = parsedData[0];
            kpis = Object.keys(firstRow)
              .filter(key => {
                const val = firstRow[key];
                return typeof val === "number" || (typeof val === "string" && !isNaN(Number(val)) && val.trim() !== "");
              })
              .map(key => ({
                label: key,
                value: Number(firstRow[key])
              }));
          }

              formattedMessages.push({
                id: msg.id || Date.now().toString(),
                role: "assistant",
                type: msg.sql_query ? "ANALYTICS" : "GENERAL",
                content: msg.message_text,
                business_summary: msg.business_summary,
                followup_questions:
                msg.followup_questions || [],
                sql_query: msg.sql_query,
                data: parsedData,
                chart: chartMetadata,
                kpis: kpis
              });
        }
      });

      setMessages(formattedMessages);
      setSelectedSessionId(sessionId);
    } catch (error) {
      console.error(error);
    }
  };

  const askQuestion = async (qText) => {
    const queryToSend = qText || question;
    if (!queryToSend) {
      message.warning("Please enter a question");
      return;
    }

    let currentSessionId = selectedSessionId;
    if (!currentSessionId) {
      try {
        const response = await fetch(`${API}/chat-sessions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify({
            session_name: queryToSend.substring(0, 30)
          })
        });
        const sessionData = await response.json();
        currentSessionId = sessionData.id;
        setSelectedSessionId(currentSessionId);
        await loadChatSessions(false);
      } catch (error) {
        message.error("Unable to create chat session");
        return;
      }
    }

    const userMsg = {
      id: Date.now().toString(),
      role: "user",
      content: queryToSend,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    setQuestion("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/ask?question=${encodeURIComponent(queryToSend)}&session_id=${currentSessionId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.status === 401) {
        message.error("Session expired.");
        return;
      }

      const data = await res.json();
      setLoading(false);

      if (data.error) {
        const errorMsg = {
          id: Date.now().toString(),
          role: "assistant",
          content: data.error,
          error: data.error,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, errorMsg]);
        return;
      }

      const aiMsg = {
        id: Date.now().toString(),
        role: "assistant",
        type: data.type || "ANALYTICS",
        content: data.message || data.business_summary,
        business_summary: data.business_summary,
        followup_questions:
        data.followup_questions || [],
        sql_query: data.sql_query,
        chart: data.chart,
        data: data.data,
        chart_data: data.chart_data,
        timestamp: new Date(),
        kpis: data.kpis
      };

      setMessages(prev => [...prev, aiMsg]);
    } catch (error) {
      setLoading(false);
      const errorMsg = {
        id: Date.now().toString(),
        role: "assistant",
        content: "Error communicating with AI Analytics engine.",
        error: "Connection down",
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMsg]);
    }
  };

  const handleSuggestedQuestion = (
    question
    ) => {

    askQuestion(question);

  };

  const startNewChat = async () => {
    try {
      const response = await fetch(`${API}/chat-sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          session_name: `New Chat ${new Date().toLocaleString()}`
        })
      });
      const data = await response.json();
      setSelectedSessionId(data.id);
      setMessages([]);
      setQuestion("");
      loadChatSessions(false);
    } catch (error) {
      console.error(error);
    }
  };

  const handleOpenRename = (chat, e) => {
    e.stopPropagation();
    setRenameChatId(chat.id);
    setRenameChatName(chat.session_name);
    setIsRenameModalOpen(true);
  };

  const saveRenameChat = async () => {
    try {
      const response = await fetch(`${API}/chat-sessions/${renameChatId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ session_name: renameChatName })
      });
      if (!response.ok) {
        message.error("Failed to rename chat");
        return;
      }
      await loadChatSessions(false);
      setIsRenameModalOpen(false);
    } catch (error) {
      console.error(error);
    }
  };

  const deleteHistoryChat = async (id, e) => {
    e.stopPropagation();
    try {
      const response = await fetch(`${API}/chat-sessions/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) {
        message.error("Failed to delete chat");
        return;
      }
      if (selectedSessionId === id) {
        setMessages([]);
        setSelectedSessionId(null);
      }
      await loadChatSessions(false);
    } catch (error) {
      console.error(error);
    }
  };

  const downloadExcel = async (q, summary, dataList) => {
    try {
      const res = await fetch(`${API}/export-excel`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          question: q,
          summary: summary,
          data: dataList
        })
      });
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Retail_Analytics_${q.substring(0, 15).replace(/[^a-zA-Z0-9]/g, "_")}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch {
      message.error("Failed to download Excel");
    }
  };

  const toggleVoiceInput = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      message.error("Speech recognition is not supported in this browser.");
      return;
    }
    if (isListening) {
      if (recognitionRef.current) recognitionRef.current.stop();
      setIsListening(false);
      return;
    }
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => setQuestion(event.results[0][0].transcript);
    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  const renderWelcomeDashboard = () => {
    const suggestionInfo = [
      {
        title: "Identify top selling product categories",
        desc: "Identify top selling product categories",
        icon: <RocketOutlined style={{ color: "#10b981", fontSize: "18px" }} />
      },
      {
        title: "Show sales distribution by Region",
        desc: "Compare regional performance metrics in charts.",
        icon: <BarChartOutlined style={{ color: "#6366f1", fontSize: "18px" }} />
      },
      {
        title: "Top cities by reseller sales",
        desc: "Find geographic clusters with peak reseller volume.",
        icon: <BulbOutlined style={{ color: "#f59e0b", fontSize: "18px" }} />
      },
      {
        title: "Monthly target achievement",
        desc: "Track sales performance against key monthly targets.",
        icon: <CheckCircleOutlined style={{ color: "#ec4899", fontSize: "18px" }} />
      }
    ];

    return (
      <div style={{ maxWidth: "800px", margin: "40px auto", padding: "0 20px" }}>
        <div style={{ textAlign: "center", marginBottom: "40px" }}>
          <Avatar
            size={64}
            icon={<DatabaseOutlined />}
            style={{ backgroundColor: "#4f46e5", marginBottom: "16px" }}
          />
          <div>
            <Title level={2} className="gradient-title" style={{ margin: 0, fontWeight: 800 }}>
              Retail Intelligence Copilot
            </Title>
          </div>
          <Paragraph style={{ fontSize: "15px", marginTop: "12px", color: "var(--text-muted)", lineHeight: "1.6" }}>
            Query your sales and operations database in natural English. Ask questions about revenue, customer transactions, stock items, or performance stats.
          </Paragraph>
        </div>

        <Row gutter={[16, 16]} style={{ marginBottom: "40px" }}>
          <Col xs={24} sm={8}>
            <div style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "10px",
              padding: "16px",
              display: "flex",
              alignItems: "center",
              gap: "12px",
              height: "100%"
            }}>
              <DatabaseOutlined style={{ color: "#6366f1", fontSize: "20px" }} />
              <div>
                <div style={{ color: "var(--text-muted)", fontSize: "11px", fontWeight: 600, textTransform: "uppercase" }}>Dataset</div>
                <div style={{ color: "var(--text-main)", fontSize: "14.5px", fontWeight: 700 }}>Custom</div>
              </div>
            </div>
          </Col>
          <Col xs={24} sm={8}>
            <div style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "10px",
              padding: "16px",
              display: "flex",
              alignItems: "center",
              gap: "12px",
              height: "100%"
            }}>
              <CheckCircleOutlined style={{ color: "#10b981", fontSize: "20px" }} />
              <div>
                <div style={{ color: "var(--text-muted)", fontSize: "11px", fontWeight: 600, textTransform: "uppercase" }}>Security Policies</div>
                <div style={{ color: "var(--text-main)", fontSize: "14.5px", fontWeight: 700 }}>Active (RLS)</div>
              </div>
            </div>
          </Col>
          <Col xs={24} sm={8}>
            <div style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-color)",
              borderRadius: "10px",
              padding: "16px",
              display: "flex",
              alignItems: "center",
              gap: "12px",
              height: "100%"
            }}>
              <SmileOutlined style={{ color: "#ec4899", fontSize: "20px" }} />
              <div>
                <div style={{ color: "var(--text-muted)", fontSize: "11px", fontWeight: 600, textTransform: "uppercase" }}>Copilot Mode</div>
                <div style={{ color: "var(--text-main)", fontSize: "14.5px", fontWeight: 700 }}>Enterprise AI</div>
              </div>
            </div>
          </Col>
        </Row>

        <Title level={4} style={{ marginBottom: "20px", color: "var(--text-main)", fontWeight: 700 }}>
          Suggested Retail Analytics Queries
        </Title>
        <Row gutter={[12, 12]}>
          {suggestionInfo.map((item, i) => (
            <Col xs={24} sm={12} key={i}>
              <div
                onClick={() => askQuestion(item.title)}
                className="welcome-suggestion-card"
                style={{
                  borderRadius: "12px",
                  background: "var(--bg-card)",
                  border: "1px solid var(--border-color)",
                  padding: "16px",
                  cursor: "pointer",
                  height: "100%",
                  display: "flex",
                  gap: "14px",
                  transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)"
                }}
              >
                <div style={{ flexShrink: 0, background: "var(--bg-card-inner)", padding: "10px", borderRadius: "8px", height: "fit-content" }}>
                  {item.icon}
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px", overflow: "hidden" }}>
                  <Text strong style={{ fontSize: "13.5px", color: "var(--text-main)" }} ellipsis={{ tooltip: item.title }}>{item.title}</Text>
                  <Text style={{ fontSize: "12px", color: "var(--text-muted)" }}>{item.desc}</Text>
                </div>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <ArrowRightOutlined className="arrow-hover-icon" style={{ color: "var(--text-muted)", transition: "all 0.2s" }} />
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </div>
    );
  };

  const formatTableCell = (val, key) => {
    if (val === null || val === undefined) return <span style={{ color: "var(--text-muted)" }}>-</span>;
    if (typeof val === "number") {
      const keyLower = key.toLowerCase();
      
      // Percentage formatting
      if (keyLower.includes("margin") || keyLower.includes("percent") || keyLower.includes("rate") || keyLower.includes("ratio") || keyLower.includes("pct")) {
        const pctVal = (val > 0 && val < 1) ? val * 100 : val;
        return <span style={{ fontFamily: "monospace", color: "var(--code-blue)" }}>{pctVal.toFixed(1)}%</span>;
      }
      
      // Check currency
      const isCurrency = keyLower.includes("sales") || 
                         keyLower.includes("revenue") || 
                         keyLower.includes("cost") || 
                         keyLower.includes("profit") || 
                         keyLower.includes("amount") ||
                         keyLower.includes("price") ||
                         keyLower.includes("value");
                         
      let formattedVal = val;
      let suffix = "";
      
      if (Math.abs(val) >= 1_000_000_000) {
        formattedVal = val / 1_000_000_000;
        suffix = "B";
      } else if (Math.abs(val) >= 1_000_000) {
        formattedVal = val / 1_000_000;
        suffix = "M";
      } else if (Math.abs(val) >= 1_000) {
        formattedVal = val / 1_000;
        suffix = "K";
      }
      
      let valStr;
      if (suffix !== "") {
        valStr = formattedVal.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + suffix;
      } else {
        valStr = val.toLocaleString(undefined, { maximumFractionDigits: 2 });
      }
      
      return (
        <span style={{ fontFamily: "monospace", color: "var(--code-blue)", fontWeight: 600 }}>
          {isCurrency ? `$${valStr}` : valStr}
        </span>
      );
    }
    
    // Text formatting
    return <span style={{ color: "var(--text-main)" }}>{String(val)}</span>;
  };

  const tableColumns = (data) => {
    if (!data || !data.length) return [];
    
    const sampleRow = data[0];
    return Object.keys(sampleRow).map(key => {
      const isNum = typeof sampleRow[key] === "number";
      return {
        title: key === "" ? "Value" : key,
        dataIndex: key,
        key: key,
        align: isNum ? "right" : "left",
        sorter: (a, b) => {
          const valA = a[key];
          const valB = b[key];
          if (typeof valA === "number" && typeof valB === "number") {
            return valA - valB;
          }
          return String(valA).localeCompare(String(valB));
        },
        render: (val, record) => formatTableCell(record[key], key)
      };
    });
  };

  return (
    <Layout hasSider style={{ height: "calc(100vh - 112px)", background: "var(--bg-chat-session)", flexDirection: "row", overflow: "hidden" }}>
      <Sider
        width={260}
        style={{
          background: "var(--bg-chat-session)",
          borderRight: "1px solid var(--border-color)",
          display: "flex",
          flexDirection: "column",
          height: "100%",
          overflowY: "auto"
        }}
      >
        <div style={{ padding: "16px", borderBottom: "1px solid var(--border-color)" }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            onClick={startNewChat}
            style={{ height: "40px", borderRadius: "8px", fontWeight: 600, backgroundColor: "#4f46e5" }}
          >
            New Chat Session
          </Button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "12px 8px" }}>
          <List
            size="small"
            dataSource={historyChats}
            renderItem={(item) => (
              <div
                onClick={() => loadSessionMessages(item.id)}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "10px 12px",
                  borderRadius: "6px",
                  cursor: "pointer",
                  marginBottom: "4px",
                  backgroundColor: selectedSessionId === item.id ? "var(--bg-selected-chat)" : "transparent",
                }}
                className="history-chat-item"
              >
                <Space size="small" style={{ overflow: "hidden" }}>
                  <MessageOutlined style={{ color: "#6366f1" }} />
                  <Text style={{ color: "var(--text-main)", fontSize: "13px" }} ellipsis={{ tooltip: item.session_name }}>
                     {item.session_name}
                  </Text>
                </Space>
                
                <Space className="history-actions" size={2}>
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined style={{ color: "var(--text-muted)" }} />}
                    onClick={(e) => handleOpenRename(item, e)}
                  />
                  <Popconfirm
                    title="Delete Chat?"
                    onConfirm={(e) => deleteHistoryChat(item.id, e)}
                    onCancel={(e) => e.stopPropagation()}
                    dropdownStyle={{ background: "var(--border-color)" }}
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>
                </Space>
              </div>
            )}
          />
        </div>
      </Sider>

      <Content style={{ display: "flex", flexDirection: "column", height: "100%", background: "var(--bg-layout)", overflow: "hidden" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 16px", scrollBehavior: "smooth" }}>
          {messages.length === 0 ? (
            renderWelcomeDashboard()
          ) : (
            <div style={{ maxWidth: "100%", width: "100%", margin: "0 auto" }}>
              {messages.map((msg, index) => {
                const isUser = msg.role === "user";
                return (
                  <div key={index} className="fade-in-message" style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: "24px" }}>
                    {isUser ? (
                      <div style={{ 
                        maxWidth: "70%", 
                        background: "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)", 
                        color: "#ffffff", 
                        padding: "12px 18px", 
                        borderRadius: "16px 16px 2px 16px",
                        boxShadow: "0 2px 8px rgba(79, 70, 229, 0.15)",
                        display: "flex",
                        flexDirection: "column",
                        gap: "4px"
                      }}>
                        <Text style={{ color: "#ffffff", fontSize: "14.5px" }}>{msg.content}</Text>
                        <div style={{ fontSize: "10px", color: "rgba(255, 255, 255, 0.7)", textAlign: "right" }}>
                          {formatMessageTime(msg.timestamp)}
                        </div>
                      </div>
                    ) : (
                      <div style={{ width: "100%", maxWidth: (msg.type === "GENERAL" || msg.error) ? "85%" : "100%" }}>
                        {msg.error ? (
                          <div className="fade-in-message">
                            <Alert message="Security Policy Violation" description={msg.content} type="error" showIcon />
                          </div>
                        ) : msg.type === "GENERAL" ? (
                          <Card 
                            bordered={false} 
                            style={{ 
                              background: "var(--bg-card)", 
                              border: "1px solid var(--border-color)", 
                              borderRadius: "12px",
                              boxShadow: "0 2px 8px rgba(0, 0, 0, 0.02)"
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                              <Space align="start">
                                <Avatar style={{ backgroundColor: "#6366f1" }} icon={<SmileOutlined />} />
                                <div>
                                  <Text strong style={{ color: "var(--text-main)" }}>AI Assistant</Text>
                                  <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                                    {formatMessageTime(msg.timestamp)}
                                  </div>
                                  <div style={{ marginTop: "8px", color: "var(--text-secondary)", fontSize: "14px", lineHeight: "1.5" }}>
                                    {msg.content}
                                  </div>
                                </div>
                              </Space>
                              <Tooltip title="Copy Response">
                                <Button 
                                  type="text" 
                                  size="small" 
                                  icon={<CopyOutlined style={{ color: "var(--text-muted)" }} />} 
                                  onClick={() => copyTextToClipboard(msg.content, "Response")}
                                />
                              </Tooltip>
                            </div>
                          </Card>
                        ) : (
                          <AnalyticsWorkspace
                            msg={msg}
                            userInfo={userInfo}
                            downloadExcel={downloadExcel}
                            askQuestion={handleSuggestedQuestion}
                            tableColumns={tableColumns}
                            formatMessageTime={formatMessageTime}
                          />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              {loading && (
                <div 
                  className="fade-in-message"
                  style={{ 
                    display: "flex", 
                    flexDirection: "column", 
                    gap: "16px", 
                    marginBottom: "24px",
                    width: "100%" 
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <Avatar style={{ backgroundColor: "#6366f1" }} icon={<LoadingOutlined spin />} />
                    <div>
                      <Text strong style={{ color: "var(--text-main)", fontSize: "14px" }}>AI Business Assistant</Text>
                      <div className="thinking-dots" style={{ fontSize: "12px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "4px" }}>
                        <span>Thinking</span>
                        <span className="dot">.</span>
                        <span className="dot">.</span>
                        <span className="dot">.</span>
                      </div>
                    </div>
                  </div>
                  
                  <div style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "12px",
                    padding: "24px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "20px"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px", width: "40%" }}>
                        <div className="pulse-skeleton" style={{ height: "16px", borderRadius: "4px", width: "100%" }} />
                        <div className="pulse-skeleton" style={{ height: "12px", borderRadius: "4px", width: "60%" }} />
                      </div>
                      <div className="pulse-skeleton" style={{ height: "32px", borderRadius: "6px", width: "100px" }} />
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                      <div className="pulse-skeleton" style={{ height: "14px", borderRadius: "4px", width: "95%" }} />
                      <div className="pulse-skeleton" style={{ height: "14px", borderRadius: "4px", width: "90%" }} />
                      <div className="pulse-skeleton" style={{ height: "14px", borderRadius: "4px", width: "80%" }} />
                    </div>

                    <Row gutter={12}>
                      {[1, 2, 3, 4].map(k => (
                        <Col span={6} key={k}>
                          <div style={{
                            background: "var(--bg-card-inner)",
                            border: "1px solid var(--border-color)",
                            borderRadius: "8px",
                            padding: "16px",
                            display: "flex",
                            flexDirection: "column",
                            gap: "8px"
                          }}>
                            <div className="pulse-skeleton" style={{ height: "12px", borderRadius: "4px", width: "50%" }} />
                            <div className="pulse-skeleton" style={{ height: "24px", borderRadius: "4px", width: "70%" }} />
                          </div>
                        </Col>
                      ))}
                    </Row>

                    <div style={{
                      background: "var(--bg-card-inner)",
                      border: "1px solid var(--border-color)",
                      borderRadius: "8px",
                      height: "180px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center"
                    }}>
                      <div className="pulse-skeleton" style={{ height: "60%", width: "80%", borderRadius: "4px" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div style={{ padding: "16px 24px", background: "var(--bg-chat-session)", borderTop: "1px solid var(--border-color)" }}>
          <div style={{ maxWidth: "850px", width: "100%", margin: "0 auto", display: "flex", gap: "12px" }}>
            <Input
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onPressEnter={() => askQuestion()}
              placeholder="Ask a question about sales, products, or customers..."
              style={{ background: "var(--bg-chat-input)", borderColor: "var(--border-chat-input)" }}
              suffix={
                <Button 
                  type="text" 
                  icon={isListening ? <AudioOutlined style={{ color: "#ef4444" }} /> : <AudioOutlined style={{ color: "var(--text-muted)" }} />} 
                  onClick={toggleVoiceInput} 
                />
              }
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={() => askQuestion()}
              style={{ backgroundColor: "#4f46e5" }}
            />
          </div>
        </div>
      </Content>

      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Rename Chat Session</span>}
        open={isRenameModalOpen}
        onOk={saveRenameChat}
        onCancel={() => setIsRenameModalOpen(false)}
        styles={{ body: { backgroundColor: "var(--bg-card)" } }}
      >
        <Input value={renameChatName} onChange={e => setRenameChatName(e.target.value)} />
      </Modal>
    </Layout>
  );
}
