import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Table, Card, Tag, Button, Space, Typography, Alert, Modal,
  Form, Input, Select, Switch, Tooltip, Badge, Row, Col, Divider
} from "antd";
import {
  SearchOutlined, ClearOutlined, ReloadOutlined, EditOutlined,
  DeleteOutlined, CheckOutlined, CloseOutlined, ThunderboltOutlined,
  ArrowRightOutlined, BulbOutlined, CheckCircleOutlined, StopOutlined,
  UndoOutlined, PlusOutlined
} from "@ant-design/icons";

import { message } from "../../utils/message";
import { modal } from "../../utils/modal";
import {
  getColumnState,
  getSuggestions,
  confirmSuggestion,
  rejectSuggestion,
  getConfigOptions,
  generateSuggestions,
  getGenerationStatus,
  updateMetricConfig,
  updateDimensionConfig,
  createMetricDefinition,
  createDimensionDefinition
} from "../../services/semanticConfigService";

import EvidencePanel from "./EvidencePanel";

const { Text, Paragraph } = Typography;
const { Option } = Select;

const provisionalStyle = {
  fontStyle: "italic",
  color: "var(--text-secondary)"
};

const getColumnKey = (tableName, columnName) =>
  `${(tableName || "").toLowerCase().trim()}.${(columnName || "").toLowerCase().trim()}`;

export default function ColumnsWorkbench({ API, token, canEdit, onUpdated, reloadSignal }) {
  const [loading, setLoading] = useState(false);
  const [unifiedColumns, setUnifiedColumns] = useState([]);
  const [columnState, setColumnState] = useState({ metrics: {}, dimensions: {} });
  const [suggestionsData, setSuggestionsData] = useState(null);
  const [options, setOptions] = useState({ dimension_roles: [] });

  // Filters
  const [searchText, setSearchText] = useState("");
  const [tableFilter, setTableFilter] = useState("ALL");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  // Review & Edit Modal. `createMode` reuses the same modal/form to add a
  // brand-new definition for a column discovery never registered.
  const [editingRow, setEditingRow] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [createMode, setCreateMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formClass, setFormClass] = useState("MEASURE");
  const [form] = Form.useForm();

  // Suggestion Generation
  const [generation, setGeneration] = useState(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [runTables, setRunTables] = useState([]);
  const [useModel, setUseModel] = useState(true);
  const [pollNonce, setPollNonce] = useState(0);
  const previousRunStatus = useRef(null);

  const running = generation?.status === "RUNNING";

  // Data Loader
  const loadData = useCallback(async () => {
    if (!token) return;
    setLoading(true);

    try {
      const [metricsRes, dimsRes, stateRes, suggRes, optRes] = await Promise.allSettled([
        fetch(`${API}/semantic/metrics`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API}/semantic/dimensions`, { headers: { Authorization: `Bearer ${token}` } }),
        getColumnState(API, token),
        getSuggestions(API, token),
        getConfigOptions(API, token)
      ]);

      let metricsList = [];
      if (metricsRes.status === "fulfilled" && metricsRes.value.ok) {
        metricsList = await metricsRes.value.json();
      }

      let dimsList = [];
      if (dimsRes.status === "fulfilled" && dimsRes.value.ok) {
        dimsList = await dimsRes.value.json();
      }

      let stateObj = { metrics: {}, dimensions: {} };
      if (stateRes.status === "fulfilled" && stateRes.value) {
        const s = stateRes.value;
        stateObj = {
          metrics: Object.fromEntries((s.metrics || []).map(m => [m.metric_id, m])),
          dimensions: Object.fromEntries((s.dimensions || []).map(d => [d.dimension_id, d]))
        };
      }

      let suggObj = null;
      if (suggRes.status === "fulfilled" && suggRes.value) {
        suggObj = suggRes.value;
      }

      if (optRes.status === "fulfilled" && optRes.value) {
        setOptions(optRes.value);
      }

      setColumnState(stateObj);
      setSuggestionsData(suggObj);

      // Construct Unified Physical Columns List
      const columnMap = new Map();

      // 1. Metrics
      (metricsList || []).forEach(m => {
        const key = getColumnKey(m.table_name, m.column_name);
        const st = stateObj.metrics[m.metric_id] || {};
        columnMap.set(key, {
          key,
          table_name: m.table_name,
          column_name: m.column_name,
          metric_id: m.metric_id,
          dimension_id: null,
          classification: "MEASURE",
          business_name: m.business_name || m.column_name,
          technical_name: m.metric_name || m.column_name,
          synonyms: m.synonyms || "",
          description: m.description || "",
          aggregation_type: m.aggregation_type || "SUM",
          dimension_role: null,
          source: m.source || "MANUAL",
          is_active: m.is_active !== undefined ? m.is_active : true,
          is_excluded: st.is_excluded ?? false,
          is_confirmed: st.is_confirmed ?? false,
          has_config: true,
          suggestion: null
        });
      });

      // 2. Dimensions
      (dimsList || []).forEach(d => {
        const key = getColumnKey(d.table_name, d.column_name);
        const st = stateObj.dimensions[d.dimension_id] || {};
        if (columnMap.has(key)) {
          const existing = columnMap.get(key);
          existing.dimension_id = d.dimension_id;
          existing.dimension_role = st.dimension_role || null;
        } else {
          columnMap.set(key, {
            key,
            table_name: d.table_name,
            column_name: d.column_name,
            metric_id: null,
            dimension_id: d.dimension_id,
            classification: "DIMENSION",
            business_name: d.business_name || d.column_name,
            technical_name: d.dimension_name || d.column_name,
            synonyms: d.synonyms || "",
            description: d.description || "",
            aggregation_type: null,
            dimension_role: st.dimension_role || null,
            source: d.source || "MANUAL",
            is_active: d.is_active !== undefined ? d.is_active : true,
            is_excluded: st.is_excluded ?? false,
            is_confirmed: st.is_confirmed ?? false,
            has_config: true,
            suggestion: null
          });
        }
      });

      // 3. Suggestions
      const colSuggestions = suggObj?.column_suggestions || [];
      colSuggestions.forEach(s => {
        const key = getColumnKey(s.table_name, s.column_name);
        if (columnMap.has(key)) {
          const existing = columnMap.get(key);
          existing.suggestion = s;
          if (s.review_status === "CONFIRMED") {
            existing.is_confirmed = true;
          }
        } else {
          const proposal = s.proposal || {};
          const current = s.current || {};
          
          let suggClass = proposal.classification || current.classification || "DIMENSION";
          if (suggClass !== "MEASURE" && suggClass !== "DIMENSION") {
            suggClass = "DIMENSION";
          }

          columnMap.set(key, {
            key,
            table_name: s.table_name,
            column_name: s.column_name,
            metric_id: null,
            dimension_id: null,
            classification: suggClass,
            business_name: current.business_name || proposal.business_name || s.column_name,
            technical_name: s.column_name,
            synonyms: Array.isArray(proposal.synonyms)
              ? proposal.synonyms.join(", ")
              : (proposal.synonyms || ""),
            description: proposal.description || "",
            aggregation_type: proposal.aggregation_type || null,
            dimension_role: proposal.dimension_role || null,
            source: "AUTO",
            is_active: true,
            is_excluded: current.is_excluded ?? proposal.is_excluded ?? false,
            is_confirmed: s.review_status === "CONFIRMED",
            has_config: false,
            suggestion: s
          });
        }
      });

      const unifiedList = Array.from(columnMap.values());
      setUnifiedColumns(unifiedList);
    } catch (err) {
      console.error(err);
      message.error(`Error loading columns workbench: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  }, [API, token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Parent (SemanticLayer) bumps reloadSignal after a discovery run so the
  // workbench picks up the freshly discovered columns. Skipped on first mount,
  // which the effect above already covers.
  const firstReloadSignal = useRef(true);
  useEffect(() => {
    if (firstReloadSignal.current) {
      firstReloadSignal.current = false;
      return;
    }
    loadData();
  }, [reloadSignal, loadData]);

  // Polling for Suggestion Generation
  useEffect(() => {
    let cancelled = false;
    let timer = null;

    const poll = async () => {
      try {
        const state = await getGenerationStatus(API, token);
        if (cancelled) return;

        const was = previousRunStatus.current;
        previousRunStatus.current = state.status;
        setGeneration(state);

        if (was === "RUNNING" && state.status === "SUCCEEDED") {
          message.success(state.message, 8);
          loadData();
        }
        if (was === "RUNNING" && state.status === "FAILED") {
          message.error(state.message, 12);
        }
        if (state.status === "RUNNING") {
          timer = setTimeout(poll, 5000);
        }
      } catch (e) {
        // Silent poll error handling
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [API, token, loadData, pollNonce]);

  const handleGenerate = async () => {
    setStarting(true);
    try {
      const state = await generateSuggestions(API, token, {
        tableNames: runTables,
        useModel
      });

      previousRunStatus.current = state.status;
      setGeneration(state);
      setGenerateOpen(false);
      message.info(state.message || "Suggestion run started.", 8);
      setPollNonce(n => n + 1);
    } catch (e) {
      message.error(`Could not start suggestion run: ${e.message}`);
    } finally {
      setStarting(false);
    }
  };

  // Distinct tables for dropdown filter
  const availableTables = Array.from(
    new Set(unifiedColumns.map(c => c.table_name).filter(Boolean))
  ).sort();

  // Filtered Columns Logic
  const filteredColumns = unifiedColumns.filter(col => {
    // Search
    const query = searchText.toLowerCase();
    const matchesSearch = !query ||
      (col.table_name || "").toLowerCase().includes(query) ||
      (col.column_name || "").toLowerCase().includes(query) ||
      (col.business_name || "").toLowerCase().includes(query) ||
      (col.synonyms || "").toLowerCase().includes(query) ||
      (col.description || "").toLowerCase().includes(query);

    // Table filter
    const matchesTable = tableFilter === "ALL" || col.table_name === tableFilter;

    // Type filter
    const matchesType = typeFilter === "ALL" || col.classification === typeFilter;

    // Status filter
    const hasPendingSugg = col.suggestion &&
      col.suggestion.review_status !== "CONFIRMED" &&
      col.suggestion.review_status !== "REJECTED";

    let matchesStatus = true;
    if (statusFilter === "PROPOSED") {
      matchesStatus = hasPendingSugg || (!col.is_confirmed && !col.is_excluded);
    } else if (statusFilter === "CONFIRMED") {
      matchesStatus = col.is_confirmed || col.suggestion?.review_status === "CONFIRMED";
    } else if (statusFilter === "EXCLUDED") {
      matchesStatus = col.is_excluded;
    }

    return matchesSearch && matchesTable && matchesType && matchesStatus;
  });

  // Open the modal to add a brand-new definition for a column that discovery
  // never registered. Reuses the same MEASURE/DIMENSION-aware form.
  const handleOpenCreate = () => {
    setCreateMode(true);
    setEditingRow(null);
    setFormClass("MEASURE");
    form.resetFields();
    form.setFieldsValue({
      table_name: "",
      column_name: "",
      business_name: "",
      classification: "MEASURE",
      synonyms: "",
      aggregation_type: "SUM",
      dimension_role: null,
      description: ""
    });
    setModalOpen(true);
  };

  // Open Edit / Review Modal
  const handleOpenReview = (record) => {
    setCreateMode(false);
    setEditingRow(record);

    const initialClass = record.classification === "MEASURE" ? "MEASURE" : "DIMENSION";
    setFormClass(initialClass);

    const proposal = record.suggestion?.proposal || {};

    const synonymsVal = record.synonyms ||
      (Array.isArray(proposal.synonyms) ? proposal.synonyms.join(", ") : proposal.synonyms) || "";

    form.setFieldsValue({
      business_name: record.business_name || proposal.business_name || record.column_name,
      technical_name: record.technical_name || record.column_name,
      classification: initialClass,
      synonyms: synonymsVal,
      aggregation_type: record.aggregation_type || proposal.aggregation_type || "SUM",
      dimension_role: record.dimension_role || proposal.dimension_role || null,
      description: record.description || proposal.description || ""
    });

    setModalOpen(true);
  };

  // Copy AI proposal into form values
  const handleApplyProposalToForm = () => {
    if (!editingRow?.suggestion?.proposal) return;
    const p = editingRow.suggestion.proposal;

    let newClass = p.classification || formClass;
    if (newClass !== "MEASURE" && newClass !== "DIMENSION") {
      newClass = "DIMENSION";
    }
    setFormClass(newClass);

    form.setFieldsValue({
      classification: newClass,
      business_name: p.business_name || form.getFieldValue("business_name"),
      synonyms: Array.isArray(p.synonyms) ? p.synonyms.join(", ") : (p.synonyms || ""),
      dimension_role: p.dimension_role || form.getFieldValue("dimension_role") || null,
      aggregation_type: p.aggregation_type || form.getFieldValue("aggregation_type") || "SUM",
      description: p.description || form.getFieldValue("description")
    });

    message.info("Copied AI proposal to form. Save & Confirm to persist.");
  };

  // Single Authoritative Exclude / Restore Action (Outside in Table Row)
  const handleToggleExclusionQuick = async (record) => {
    const targetState = !record.is_excluded;
    const actionLabel = targetState ? "Excluded" : "Restored";
    setLoading(true);

    try {
      if (record.suggestion?.suggestion_id) {
        const proposal = record.suggestion.proposal || {};
        const editedProposal = {
          classification: record.classification,
          business_name: record.business_name,
          synonyms: typeof record.synonyms === "string"
            ? record.synonyms.split(",").map(s => s.trim()).filter(Boolean)
            : record.synonyms || [],
          dimension_role: record.classification === "DIMENSION" ? (record.dimension_role || proposal.dimension_role) : null,
          aggregation_type: record.classification === "MEASURE" ? (record.aggregation_type || proposal.aggregation_type) : null,
          description: record.description || proposal.description || "",
          is_excluded: targetState
        };

        await confirmSuggestion(API, token, record.suggestion.suggestion_id, editedProposal);
      } else if (record.classification === "MEASURE" && record.metric_id) {
        await updateMetricConfig(API, token, record.metric_id, {
          is_excluded: targetState
        });
      } else if (record.classification === "DIMENSION" && record.dimension_id) {
        await updateDimensionConfig(API, token, record.dimension_id, {
          is_excluded: targetState
        });
      }

      message.success(`Column ${record.table_name}.${record.column_name} ${actionLabel}.`);
      await loadData();
      if (onUpdated) onUpdated();
    } catch (e) {
      message.error(`Action failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Submit the create form. Posts to the pre-Gate-2 create endpoints; the
  // dimension_role (not part of the create body) is applied in a follow-up
  // config PATCH only when one was chosen.
  const handleCreateDefinition = async (values) => {
    const tableName = (values.table_name || "").trim();
    const columnName = (values.column_name || "").trim();

    // The metrics create endpoint only dedups on metric_name, not on
    // table+column, so guard the real duplicate here against the list we
    // already hold. This is also the "validate identity" step: a definition
    // for this physical column must not already exist.
    const dupKey = getColumnKey(tableName, columnName);
    if (unifiedColumns.some(c => c.key === dupKey)) {
      message.error(
        `A definition for ${tableName}.${columnName} already exists. ` +
        "Edit that row instead of creating a duplicate."
      );
      return;
    }

    // Deterministic technical name, unique per table.column, so two tables
    // sharing a column name cannot collide on the connection-wide name check.
    const technicalName = `${tableName}_${columnName}`
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");

    const synonymsStr = (values.synonyms || "").trim();

    if (values.classification === "MEASURE") {
      await createMetricDefinition(API, token, {
        metric_name: technicalName,
        business_name: values.business_name,
        synonyms: synonymsStr || null,
        description: values.description || null,
        table_name: tableName,
        column_name: columnName,
        aggregation_type: values.aggregation_type,
        is_active: true
      });
      message.success(`Metric "${values.business_name}" created.`);
    } else {
      const res = await createDimensionDefinition(API, token, {
        dimension_name: technicalName,
        business_name: values.business_name,
        synonyms: synonymsStr || null,
        description: values.description || null,
        table_name: tableName,
        column_name: columnName,
        is_active: true
      });

      // dimension_role lives in the config layer, not the create body.
      if (values.dimension_role && res?.dimension_id) {
        await updateDimensionConfig(API, token, res.dimension_id, {
          dimension_role: values.dimension_role
        });
      }
      message.success(`Dimension "${values.business_name}" created.`);
    }
  };

  // Submit Modal
  const handleSaveModal = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();

      if (createMode) {
        await handleCreateDefinition(values);
        setModalOpen(false);
        setCreateMode(false);
        setEditingRow(null);
        await loadData();
        if (onUpdated) onUpdated();
        return;
      }

      // Parse synonyms array
      const synonymsArray = typeof values.synonyms === "string"
        ? values.synonyms.split(",").map(s => s.trim()).filter(Boolean)
        : values.synonyms || [];

      const targetExcluded = !!editingRow.is_excluded;

      // If suggestion exists, confirm it via suggestion API. The suggestion
      // path supports reclassification because confirmSuggestion writes to
      // whichever table the chosen classification requires.
      if (editingRow.suggestion?.suggestion_id) {
        const editedProposal = {
          classification: values.classification,
          business_name: values.business_name,
          synonyms: synonymsArray,
          dimension_role: values.classification === "DIMENSION" ? values.dimension_role : null,
          aggregation_type: values.classification === "MEASURE" ? values.aggregation_type : null,
          description: values.description || "",
          is_excluded: targetExcluded
        };

        const res = await confirmSuggestion(
          API,
          token,
          editingRow.suggestion.suggestion_id,
          editedProposal
        );

        message.success(res.message || "Column configuration confirmed.");
        if (res.warnings) res.warnings.forEach(w => message.warning(w, 8));
      } else {
        // Direct save to Metric or Dimension config endpoint. Track whether a
        // record was actually written: for an existing definition with no
        // suggestion driving it, there is no row to write into for the OTHER
        // classification, so a type flip here must fail loudly rather than
        // report a success that never happened.
        let wrote = false;

        if (values.classification === "MEASURE" && editingRow.metric_id) {
          await updateMetricConfig(API, token, editingRow.metric_id, {
            business_name: values.business_name,
            synonyms: values.synonyms,
            aggregation_type: values.aggregation_type,
            description: values.description,
            is_excluded: targetExcluded,
            is_confirmed: true
          });
          wrote = true;
        } else if (values.classification === "DIMENSION" && editingRow.dimension_id) {
          await updateDimensionConfig(API, token, editingRow.dimension_id, {
            business_name: values.business_name,
            synonyms: values.synonyms,
            dimension_role: values.dimension_role,
            description: values.description,
            is_excluded: targetExcluded,
            is_confirmed: true
          });
          wrote = true;
        }

        if (!wrote) {
          message.error(
            `This column is registered as ${editingRow.classification}, and ` +
            `changing it to ${values.classification} is not supported from here. ` +
            `To reclassify, exclude this definition and use "Add Definition" ` +
            `to create the ${values.classification} for this column.`
          );
          setSaving(false);
          return;
        }

        message.success("Column configuration updated successfully.");
      }

      setModalOpen(false);
      setEditingRow(null);
      await loadData();
      if (onUpdated) onUpdated();
    } catch (e) {
      console.error(e);
      message.error(`Save failed: ${e.message || e}`);
    } finally {
      setSaving(false);
    }
  };

  // Reject Suggestion Action
  const handleRejectSuggestionInModal = async () => {
    if (!editingRow?.suggestion?.suggestion_id) return;
    setSaving(true);
    try {
      const res = await rejectSuggestion(API, token, editingRow.suggestion.suggestion_id, null);
      message.warning(res.message || "Suggestion rejected.");
      setModalOpen(false);
      setEditingRow(null);
      await loadData();
      if (onUpdated) onUpdated();
    } catch (e) {
      message.error(`Reject failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  // Delete Record Action
  const handleDeleteRecord = async () => {
    if (!editingRow) return;

    const isAutoRow = editingRow.source === "AUTO" || !editingRow.has_config;

    modal.confirm({
      title: "Delete Column Definition",
      content: (
        <div style={{ marginTop: 8 }}>
          {isAutoRow ? (
            <span>
              This column was auto-discovered from your database schema.
              <br /><br />
              <strong>Excluding</strong> this column is recommended over deleting it. Deleting will remove its definition, but running schema discovery in the future may recreate this row.
            </span>
          ) : (
            <span>
              Are you sure you want to delete the confirmed semantic definition for <strong>"{editingRow.business_name}"</strong>?
              <br /><br />
              This will permanently remove the stored semantic configuration for this column.
            </span>
          )}
        </div>
      ),
      okText: "Delete Definition",
      okType: "danger",
      cancelText: "Cancel",
      onOk: async () => {
        try {
          const isMetric = !!editingRow.metric_id;
          const url = isMetric
            ? `${API}/semantic/metrics/${editingRow.metric_id}`
            : `${API}/semantic/dimensions/${editingRow.dimension_id}`;

          const res = await fetch(url, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}` }
          });

          if (res.ok) {
            message.success("Definition removed successfully");
            setModalOpen(false);
            setEditingRow(null);
            await loadData();
            if (onUpdated) onUpdated();
          } else {
            const errData = await res.json().catch(() => ({}));
            message.error(errData.detail || "Failed to delete definition.");
          }
        } catch (err) {
          message.error("Error deleting definition");
        }
      }
    });
  };

  // Table Columns Definition
  const columns = [
    {
      title: "Table / Column",
      key: "table_column",
      width: "22%",
      render: (_, r) => (
        <div>
          <Text style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>
            {r.table_name}
          </Text>
          <Text strong style={{ color: "var(--text-main)", fontSize: 14 }}>
            {r.column_name}
          </Text>
        </div>
      )
    },
    {
      title: "Business Name",
      dataIndex: "business_name",
      key: "business_name",
      width: "20%",
      render: (text) => (
        <Text
          title={text}
          style={{ maxWidth: 180, display: "inline-block", color: "var(--text-main)", fontWeight: 500 }}
          ellipsis={{ tooltip: text }}
        >
          {text || "-"}
        </Text>
      )
    },
    {
      title: "Classification",
      dataIndex: "classification",
      key: "classification",
      width: "12%",
      render: (val) => (
        <Tag color={val === "MEASURE" ? "blue" : "green"}>
          {val}
        </Tag>
      )
    },
    {
      title: "Status",
      key: "status",
      width: "15%",
      render: (_, r) => {
        const hasPending = r.suggestion &&
          r.suggestion.review_status !== "CONFIRMED" &&
          r.suggestion.review_status !== "REJECTED";

        if (r.is_excluded) {
          return (
            <Tag color="red" icon={<StopOutlined />}>EXCLUDED</Tag>
          );
        }

        if (hasPending) {
          return (
            <Tooltip title="AI Proposal awaiting review">
              <Tag color="orange" icon={<BulbOutlined />}>PROPOSED</Tag>
            </Tooltip>
          );
        }

        if (r.is_confirmed || r.suggestion?.review_status === "CONFIRMED") {
          return (
            <Tag color="green" icon={<CheckCircleOutlined />}>
              CONFIRMED
            </Tag>
          );
        }

        return <Tag color="blue">UNREVIEWED</Tag>;
      }
    },
    {
      title: "Config & Synonyms",
      key: "config_synonyms",
      width: "16%",
      render: (_, r) => (
        <Space direction="vertical" size={2} style={{ maxWidth: 150 }}>
          {r.classification === "MEASURE" && r.aggregation_type && (
            <Tag color="processing" style={{ fontSize: 11 }}>
              AGG: {r.aggregation_type}
            </Tag>
          )}
          {r.classification === "DIMENSION" && r.dimension_role && (
            <Tag color="purple" style={{ fontSize: 11 }}>
              ROLE: {r.dimension_role}
            </Tag>
          )}
          {r.synonyms && (
            <Text
              style={{ fontSize: 12, color: "var(--text-secondary)", maxWidth: 140, display: "inline-block" }}
              ellipsis={{ tooltip: r.synonyms }}
            >
              Syn: {r.synonyms}
            </Text>
          )}
        </Space>
      )
    },
    {
      title: "Action",
      key: "actions",
      width: "15%",
      align: "right",
      render: (_, r) => (
        <Space size={6}>
          <Tooltip title={r.is_excluded ? "Restore column to active queries" : "Exclude column from text-to-SQL queries"}>
            <Button
              size="small"
              type={r.is_excluded ? "default" : "text"}
              danger={!r.is_excluded}
              icon={r.is_excluded ? <UndoOutlined style={{ color: "#10b981" }} /> : <StopOutlined style={{ color: "#ef4444" }} />}
              onClick={() => handleToggleExclusionQuick(r)}
              disabled={!canEdit}
            >
              {r.is_excluded ? "Restore" : "Exclude"}
            </Button>
          </Tooltip>
          <Button
            type="primary"
            ghost
            size="small"
            icon={<EditOutlined />}
            disabled={!canEdit}
            onClick={() => handleOpenReview(r)}
            aria-label={`Edit or review column ${r.table_name}.${r.column_name}`}
          >
            Review
          </Button>
        </Space>
      )
    }
  ];

  const pendingCount = unifiedColumns.filter(c =>
    c.suggestion &&
    c.suggestion.review_status !== "CONFIRMED" &&
    c.suggestion.review_status !== "REJECTED"
  ).length;

  return (
    <div>
      {/* Profiling in progress alert */}
      {running && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`Profiling in progress — ${Math.round(generation?.elapsed_seconds || 0)}s elapsed`}
          description={generation?.message || "Profiling tables and discovering semantic meanings..."}
        />
      )}

      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "12px",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "16px",
          padding: "14px 16px",
          background: "var(--bg-card)",
          border: "1px solid var(--border-color)",
          borderRadius: "12px"
        }}
      >
        <Space wrap size="middle">
          <Input
            placeholder="Search column, table, business name..."
            prefix={<SearchOutlined style={{ color: "var(--text-muted)" }} />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 260 }}
            allowClear
          />

          <Select
            placeholder="Table"
            value={tableFilter}
            onChange={setTableFilter}
            style={{ width: 150 }}
          >
            <Option value="ALL">All Tables</Option>
            {availableTables.map(tbl => (
              <Option key={tbl} value={tbl}>{tbl}</Option>
            ))}
          </Select>

          <Select
            placeholder="Classification"
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 150 }}
          >
            <Option value="ALL">All Classifications</Option>
            <Option value="MEASURE">MEASURE</Option>
            <Option value="DIMENSION">DIMENSION</Option>
          </Select>

          <Select
            placeholder="Status"
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 160 }}
          >
            <Option value="ALL">All Statuses</Option>
            <Option value="PROPOSED">Unreviewed / Proposed</Option>
            <Option value="CONFIRMED">Confirmed</Option>
            <Option value="EXCLUDED">Excluded</Option>
          </Select>

          {(searchText || tableFilter !== "ALL" || typeFilter !== "ALL" || statusFilter !== "ALL") && (
            <Button
              type="link"
              icon={<ClearOutlined />}
              onClick={() => {
                setSearchText("");
                setTableFilter("ALL");
                setTypeFilter("ALL");
                setStatusFilter("ALL");
              }}
              style={{ color: "#4f46e5", padding: "0 4px" }}
            >
              Clear
            </Button>
          )}
        </Space>

        <Space wrap>
          {pendingCount > 0 && (
            <Badge count={pendingCount} color="#d97706" style={{ marginRight: 8 }} />
          )}

          <Button
            icon={<PlusOutlined />}
            onClick={handleOpenCreate}
            disabled={!canEdit}
          >
            Add Definition
          </Button>

          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => setGenerateOpen(true)}
            disabled={!canEdit || running}
            loading={running}
            style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
          >
            Generate suggestions
          </Button>

          <Button
            icon={<ReloadOutlined />}
            onClick={loadData}
            loading={loading}
          >
            Refresh
          </Button>
        </Space>
      </div>

      {/* Main Unified Table */}
      <Table
        dataSource={filteredColumns}
        columns={columns}
        rowKey="key"
        loading={loading}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showTotal: (total) => `Total ${total} columns`
        }}
        style={{ background: "var(--bg-card)" }}
        className="dark-table"
        locale={{
          emptyText: (
            <div style={{ padding: "24px", color: "var(--text-secondary)" }}>
              No semantic column definitions found matching criteria.
            </div>
          )
        }}
      />

      {/* Suggestion Generation Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Generate AI suggestions</span>}
        open={generateOpen}
        onCancel={() => setGenerateOpen(false)}
        onOk={handleGenerate}
        okText="Start profiling"
        confirmLoading={starting}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Profile connection data"
          description="Every column on the selected tables will be analyzed and proposed with business meanings, classifications, and synonyms."
        />
        <Form layout="vertical">
          <Form.Item label="Target Tables" extra="Leave empty to profile all tables.">
            <Select
              mode="multiple"
              allowClear
              placeholder="All tables"
              value={runTables}
              onChange={setRunTables}
              options={availableTables.map(t => ({ label: t, value: t }))}
            />
          </Form.Item>
          <Form.Item label="Use AI Model">
            <Switch checked={useModel} onChange={setUseModel} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Unified Review / Edit / Create Modal */}
      <Modal
        title={
          <span style={{ color: "var(--text-main)" }}>
            {createMode
              ? "Add Column Definition"
              : `Review Column: ${editingRow ? `${editingRow.table_name}.${editingRow.column_name}` : ""}`}
          </span>
        }
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setCreateMode(false);
          setEditingRow(null);
        }}
        width={740}
        style={{ top: 30 }}
        styles={{
          body: {
            backgroundColor: "var(--bg-card)",
            padding: "16px 24px",
            maxHeight: "65vh",
            overflowY: "auto"
          }
        }}
        footer={
          (editingRow || createMode) ? (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
              <Space>
                {!createMode && editingRow?.suggestion?.suggestion_id && (
                  <Button
                    danger
                    icon={<CloseOutlined />}
                    onClick={handleRejectSuggestionInModal}
                    loading={saving}
                    disabled={!canEdit}
                  >
                    Reject proposal
                  </Button>
                )}
                {!createMode && editingRow?.has_config && (
                  <Button
                    danger
                    type="text"
                    icon={<DeleteOutlined />}
                    onClick={handleDeleteRecord}
                    disabled={!canEdit}
                  >
                    Delete definition
                  </Button>
                )}
              </Space>

              <Space>
                <Button onClick={() => { setModalOpen(false); setCreateMode(false); setEditingRow(null); }}>
                  Cancel
                </Button>
                <Button
                  type="primary"
                  onClick={handleSaveModal}
                  loading={saving}
                  disabled={!canEdit}
                  icon={createMode ? <PlusOutlined /> : <CheckOutlined />}
                  style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
                >
                  {createMode ? "Create Definition" : "Save & Confirm"}
                </Button>
              </Space>
            </div>
          ) : null
        }
      >
        {(editingRow || createMode) && (
          <div>
            {/* Exclusion Alert Banner when Excluded */}
            {editingRow?.is_excluded && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
                message="Column is Excluded"
                description="This column is currently excluded from text-to-SQL query generation. To make it active, click the 'Restore' button in the Columns table action column."
              />
            )}

            {/* AI Proposal & Evidence Review Section */}
            {editingRow?.suggestion?.proposal && (
              <Card
                size="small"
                style={{
                  marginBottom: 16,
                  background: "var(--bg-subtle, #1e293b)",
                  border: "1px solid #3b82f6"
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <Text strong style={{ color: "#60a5fa" }}>
                    <BulbOutlined /> AI Suggestion Proposal
                  </Text>
                  {canEdit && (
                    <Button
                      size="small"
                      type="link"
                      icon={<ArrowRightOutlined />}
                      onClick={handleApplyProposalToForm}
                    >
                      Copy to form
                    </Button>
                  )}
                </div>

                <Row gutter={16} style={{ marginBottom: 8 }}>
                  <Col span={12}>
                    <Text style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>
                      Current Business Name
                    </Text>
                    <Text strong style={{ color: "var(--text-main)" }}>
                      {editingRow.business_name || "-"}
                    </Text>
                  </Col>
                  <Col span={12}>
                    <Text style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>
                      Proposed Business Name
                    </Text>
                    <Text style={{ ...provisionalStyle, fontWeight: 600 }}>
                      {editingRow.suggestion.proposal.business_name || "-"}
                    </Text>
                  </Col>
                </Row>

                <Row gutter={16} style={{ marginBottom: 8 }}>
                  <Col span={12}>
                    <Text style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>
                      Current Classification
                    </Text>
                    <Tag color={editingRow.classification === "MEASURE" ? "blue" : "green"}>
                      {editingRow.classification}
                    </Tag>
                  </Col>
                  <Col span={12}>
                    <Text style={{ fontSize: 12, color: "var(--text-muted)", display: "block" }}>
                      Proposed Classification
                    </Text>
                    <Tag color={editingRow.suggestion.proposal.classification === "MEASURE" ? "blue" : "green"}>
                      {editingRow.suggestion.proposal.classification}
                    </Tag>
                  </Col>
                </Row>

                {editingRow.suggestion.evidence && (
                  <EvidencePanel
                    evidence={editingRow.suggestion.evidence}
                    confidence={editingRow.suggestion.confidence}
                    reasoning={editingRow.suggestion.reasoning}
                  />
                )}
              </Card>
            )}

            {/* Authoritative Edit Form */}
            <Form
              form={form}
              layout="vertical"
            >
              {createMode && (
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item
                      name="table_name"
                      label={<span style={{ color: "var(--text-secondary)" }}>Table</span>}
                      rules={[{ required: true, message: "Table name is required" }]}
                    >
                      <Input placeholder="e.g. QB_MDJMD_SALES_5YRS_SUMMARY" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item
                      name="column_name"
                      label={<span style={{ color: "var(--text-secondary)" }}>Column</span>}
                      rules={[{ required: true, message: "Column name is required" }]}
                    >
                      <Input placeholder="e.g. CY" />
                    </Form.Item>
                  </Col>
                </Row>
              )}

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    name="business_name"
                    label={<span style={{ color: "var(--text-secondary)" }}>Business Name</span>}
                    rules={[{ required: true, message: "Business name is required" }]}
                  >
                    <Input placeholder="e.g. Sales Margin Rate" />
                  </Form.Item>
                </Col>

                <Col span={12}>
                  <Form.Item
                    name="classification"
                    label={<span style={{ color: "var(--text-secondary)" }}>Classification (Type)</span>}
                    rules={[{ required: true }]}
                  >
                    <Select
                      onChange={val => {
                        setFormClass(val);
                      }}
                    >
                      <Option value="MEASURE">MEASURE (Metric)</Option>
                      <Option value="DIMENSION">DIMENSION (Attribute)</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item
                name="synonyms"
                label={<span style={{ color: "var(--text-secondary)" }}>Synonyms (comma separated)</span>}
              >
                <Input placeholder="e.g. Margin Rate, Profit Margin" />
              </Form.Item>

              {/* Dynamic rendering based on classification */}
              {formClass === "MEASURE" ? (
                <Form.Item
                  name="aggregation_type"
                  label={<span style={{ color: "var(--text-secondary)" }}>Aggregation Type</span>}
                  rules={[{ required: true, message: "Aggregation type is required for measures" }]}
                >
                  <Select>
                    <Option value="SUM">SUM</Option>
                    <Option value="AVG">AVG</Option>
                    <Option value="COUNT">COUNT</Option>
                    <Option value="MIN">MIN</Option>
                    <Option value="MAX">MAX</Option>
                  </Select>
                </Form.Item>
              ) : (
                <Form.Item
                  name="dimension_role"
                  label={<span style={{ color: "var(--text-secondary)" }}>Dimension Role</span>}
                >
                  <Select allowClear placeholder="Select dimension role if applicable">
                    {(options.dimension_roles || []).map(r => (
                      <Option key={r} value={r}>{r}</Option>
                    ))}
                  </Select>
                </Form.Item>
              )}

              <Form.Item
                name="description"
                label={<span style={{ color: "var(--text-secondary)" }}>Description</span>}
              >
                <Input.TextArea rows={2} placeholder="Context description for query logic" />
              </Form.Item>
            </Form>
          </div>
        )}
      </Modal>
    </div>
  );
}
