import React, { useState, useEffect } from "react";
import { 
  Row, Col, Card, Statistic, Table, Tag, Badge, Button, Space, 
  Typography, Progress, List, Timeline, Segmented, Tooltip, Spin 
} from "antd";
import { 
  DatabaseOutlined, ArrowUpOutlined, ClockCircleOutlined, CheckCircleOutlined,
  ThunderboltOutlined, AlertOutlined, SafetyCertificateOutlined, MessageOutlined 
} from "@ant-design/icons";
import { 
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, 
  Tooltip as RechartTooltip, BarChart, Bar, Cell 
} from "recharts";
import { useNavigate } from "react-router-dom";

const { Title, Text, Paragraph } = Typography;

// Mock historical stats for visual excellence
const queryVolumeData = [
  { time: "09:00", volume: 120, latency: 0.9 },
  { time: "10:00", volume: 240, latency: 1.1 },
  { time: "11:00", volume: 310, latency: 1.4 },
  { time: "12:00", volume: 190, latency: 1.2 },
  { time: "13:00", volume: 220, latency: 1.1 },
  { time: "14:00", volume: 450, latency: 1.8 },
  { time: "15:00", volume: 510, latency: 1.6 },
  { time: "16:00", volume: 380, latency: 1.3 },
  { time: "17:00", volume: 290, latency: 1.0 },
];

const intentDistribution = [
  { name: "Database Query (SQL)", value: 78, color: "#6366f1" },
  { name: "General Conversation", value: 16, color: "#10b981" },
  { name: "System Admin Commands", value: 6, color: "#f59e0b" },
];

export default function Overview({ API, token }) {
  const navigate = useNavigate(); 
  const [activeSegment, setActiveSegment] = useState("Hourly");
  const [queryVolumeData, setQueryVolumeData] = useState([]);
  const [loading, setLoading] = useState(false);
  // KPI state
  const [kpis, setKpis] = useState({ totalQueries: 0, avgLatency: 0, successPct: 0, securityBlocks: 0 });
  const [kpisLoading, setKpisLoading] = useState(false);
  const [kpisError, setKpisError] = useState(null);
  const [prevTotalQueries, setPrevTotalQueries] = useState(0);

  useEffect(() => {
    const fetchTrends = async () => {
      setLoading(true);
      try {
        let groupByParam = "hour";
        if (activeSegment === "Daily") groupByParam = "day";
        if (activeSegment === "Weekly") groupByParam = "week";

        const res = await fetch(`${API}/dashboard/query-trends?group_by=${groupByParam}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          const formatted = (data.labels || []).map((label, index) => ({
            time: label,
            volume: data.query_count[index] || 0,
            latency: data.latency[index] || 0
          }));
          setQueryVolumeData(formatted);
        }
      } catch (err) {
        console.error("Failed to fetch query trends", err);
      } finally {
        setLoading(false);
      }
    };

    const fetchKpis = async () => {
      setKpisLoading(true);
      try {
        const res = await fetch(`${API}/dashboard/kpis`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          setPrevTotalQueries(kpis.totalQueries);
          setKpis({
            totalQueries: data.total_queries || 0,
            avgLatency: data.avg_latency || 0,
            successPct: data.success_pct || 0,
            securityBlocks: data.security_blocks || 0,
          });
        } else {
          setKpisError(`Failed to load KPIs: ${res.status}`);
        }
      } catch (err) {
        console.error("Error fetching KPIs", err);
        setKpisError(err.message);
      } finally {
        setKpisLoading(false);
      }
    };

    if (token) {
      fetchTrends();
      fetchKpis();
    }
  }, [activeSegment, token, API]);

  return (
    <div style={{ padding: "4px" }}>
      {/* Banner */}
      <div style={{ 
        background: "var(--bg-banner)",
        padding: "24px", 
        borderRadius: "12px", 
        border: "1px solid var(--border-banner)",
        marginBottom: "24px",
        boxShadow: "var(--shadow-banner)"
      }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={3} style={{ margin: 0, color: "var(--text-banner-main)", fontWeight: 700 }}>
              Enterprise AI Analytics 
            </Title>
            <Paragraph style={{ color: "var(--text-banner-secondary)", margin: "4px 0 0 0", fontSize: "14px" }}>
              Unified governance, schema validation, and secure LLM database execution layer.
            </Paragraph>
          </Col>
          <Col>
            <Space size="middle">
              <Badge status="processing" text={<span style={{ color: "var(--text-active)" }}>All pipelines online</span>} />
              <Button 
                type="primary" 
                icon={<MessageOutlined />}
                style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
                onClick={() => navigate("/assistant")}
              >
                Launch Assistant
              </Button>
            </Space>
          </Col>
        </Row>
      </div>

        {/* KPI Cards with live data */}
        <Row gutter={[16, 16]} style={{ marginBottom: "24px" }}>
          {/* Total Executed Queries */}
          <Col xs={24} sm={12} lg={6}>
            <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
              <Statistic
                title={<span style={{ color: "var(--text-muted)" }}>Total Executed Queries</span>}
                value={kpis.totalQueries}
                loading={kpisLoading}
                valueStyle={{ color: "var(--text-main)", fontSize: "28px", fontWeight: 700 }}
                prefix={<DatabaseOutlined style={{ color: "var(--chart-primary)", marginRight: "8px" }} />}
                suffix={kpis.totalQueries > 0 ? <span style={{ fontSize: "12px", color: "#10b981" }}><ArrowUpOutlined />{((kpis.totalQueries/prevTotalQueries-1)*100).toFixed(1)}%</span> : null}
              />
              <div style={{ marginTop: "12px", color: "var(--text-muted)", fontSize: "12px" }}>
                Across 4 connected data sources
              </div>
            </Card>
          </Col>

          {/* Avg Pipeline Latency */}
          <Col xs={24} sm={12} lg={6}>
            <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
              <Statistic
                title={<span style={{ color: "var(--text-muted)" }}>Avg Pipeline Latency (s)</span>}
                value={kpis.avgLatency}
                precision={2}
                loading={kpisLoading}
                valueStyle={{ color: "var(--text-main)", fontSize: "28px", fontWeight: 700 }}
                prefix={<ClockCircleOutlined style={{ color: "var(--chart-secondary)", marginRight: "8px" }} />}
              />
              <div style={{ marginTop: "12px", color: "var(--text-muted)", fontSize: "12px" }}>
                Intent classification to summary delivery
              </div>
            </Card>
          </Col>

          {/* SQL Pipeline Success */}
          <Col xs={24} sm={12} lg={6}>
            <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
              <Statistic
                title={<span style={{ color: "var(--text-muted)" }}>SQL Pipeline Success</span>}
                value={kpis.successPct}
                precision={2}
                loading={kpisLoading}
                valueStyle={{ color: "var(--text-main)", fontSize: "28px", fontWeight: 700 }}
                prefix={<CheckCircleOutlined style={{ color: "#10b981", marginRight: "8px" }} />}
                suffix="%"
              />
              <div style={{ marginTop: "12px", color: "var(--text-muted)", fontSize: "12px" }}>
                0 schema validation errors today
              </div>
            </Card>
          </Col>

          {/* Security Policy Blocks */}
          <Col xs={24} sm={12} lg={6}>
            <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
              <Statistic
                title={<span style={{ color: "var(--text-muted)" }}>Security Policy Blocks</span>}
                value={kpis.securityBlocks}
                loading={kpisLoading}
                valueStyle={{ color: "#f59e0b", fontSize: "28px", fontWeight: 700 }}
                prefix={<SafetyCertificateOutlined style={{ color: "#f59e0b", marginRight: "8px" }} />}
              />
              <div style={{ marginTop: "12px", color: "var(--text-muted)", fontSize: "12px" }}>
                RLS / CLS data restrictions enforced
              </div>
            </Card>
          </Col>
        </Row>

      {/* Main Content Layout */}
      <Row gutter={[16, 16]}>
        {/* Left Column: Charts */}
        <Col span={24}>
          <Card 
            title={<span style={{ color: "var(--text-main)" }}>Query Volume & Latency Trend</span>}
            bordered={false} 
            style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", marginBottom: "16px" }}
            extra={
              <Segmented 
                options={["Hourly", "Daily", "Weekly"]} 
                value={activeSegment} 
                onChange={setActiveSegment}
                style={{ background: "var(--border-color)", color: "var(--text-main)" }}
              />
            }
          >
            <div style={{ width: "100%", height: 260, position: "relative" }}>
              <Spin spinning={loading}>
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={queryVolumeData}>
                    <defs>
                      <linearGradient id="colorVolume" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--chart-primary)" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="var(--chart-primary)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                    <XAxis dataKey="time" stroke="var(--text-muted)" />
                    <YAxis yAxisId="left" stroke="var(--chart-primary)" label={{ value: 'Queries', angle: -90, position: 'insideLeft', fill: 'var(--chart-primary)' }} />
                    <YAxis yAxisId="right" orientation="right" stroke="var(--chart-secondary)" label={{ value: 'Latency (s)', angle: 90, position: 'insideRight', fill: 'var(--chart-secondary)' }} />
                    <RechartTooltip contentStyle={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-color)", color: "var(--text-main)", borderRadius: "8px", boxShadow: "var(--shadow-banner)" }} />
                    <Area yAxisId="left" type="monotone" dataKey="volume" name="Queries" stroke="var(--chart-primary)" fillOpacity={1} fill="url(#colorVolume)" strokeWidth={2} />
                    <Area yAxisId="right" type="monotone" dataKey="latency" name="Latency" stroke="var(--chart-secondary)" fill="transparent" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </Spin>
            </div>
          </Card>
 
          {/* Connected Data Sources */}
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <Card 
                title={<span style={{ color: "var(--text-main)" }}>System Infrastructure</span>} 
                bordered={false}
                style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}
              >
                <List
                  itemLayout="horizontal"
                  dataSource={[
                    { title: "Primary Database", desc: "SQL Server (dw-prod-01)", status: "healthy", label: " Driver" },
                    { title: "Semantic Store", desc: "Azure Synapse (sem-layer)", status: "healthy", label: "Semantic layer" },
                    { title: "Metadata Cache", desc: "Redis Cache (cached-schema)", status: "healthy", label: "In-memory cache" }
                  ]}
                  renderItem={(item) => (
                    <List.Item style={{ padding: "8px 0", borderBottom: "1px solid var(--border-color)" }}>
                      <List.Item.Meta
                        avatar={<DatabaseOutlined style={{ color: "#6366f1", fontSize: "18px", marginTop: "4px" }} />}
                        title={<span style={{ color: "var(--text-main)", fontWeight: 600 }}>{item.title}</span>}
                        description={<span style={{ color: "var(--text-muted)", fontSize: "12px" }}>{item.desc}</span>}
                      />
                      <Space direction="vertical" align="end" size={2}>
                        <Badge status="success" text={<span style={{ color: "#10b981", fontSize: "12px" }}>Active</span>} />
                        <Tag color="blue" bordered={false} style={{ fontSize: "10px", margin: 0 }}>{item.label}</Tag>
                      </Space>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card 
                title={<span style={{ color: "var(--text-main)" }}>Active LLM Provider Status</span>} 
                bordered={false}
                style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                  <div>
                    <Text style={{ color: "var(--text-main)", fontWeight: 600, display: "block" }}>Groq Cloud API</Text>
                    <Text type="secondary" style={{ fontSize: "12px" }}>Primary Router (Llama-3.3-70b-specdec)</Text>
                  </div>
                  <Tag color="success" bordered={false}>Healthy</Tag>
                </div>
                <div style={{ marginBottom: "12px" }}>
                  <div style={{ display: "flex", justify: "space-between", fontSize: "12px", color: "var(--text-muted)", marginBottom: "4px" }}>
                    <span>API Quota Used (Tpm)</span>
                    <span>42,100 / 100,000</span>
                  </div>
                  <Progress percent={42} strokeColor="var(--chart-primary)" trailColor="var(--border-color)" showInfo={false} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--text-muted)" }}>
                  <span>Avg LLM API Latency: 280ms</span>
                  <span>99.9% uptime</span>
                </div>
              </Card>
            </Col>
          </Row>
        </Col>
      </Row>
    </div>
  );
}
