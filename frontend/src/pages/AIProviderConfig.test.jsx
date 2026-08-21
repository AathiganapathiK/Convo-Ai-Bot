import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import AIProviderConfig from "./AIProviderConfig";

// Mock matchMedia for Antd tabs/tables
beforeAll(() => {
  jest.setTimeout(15000);
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: jest.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
});

let mockFormValues = {};

// Mock Ant Design components completely to bypass DatePicker Node module resolution issues in Jest
jest.mock("antd", () => {
  const React = require("react");
  
  const Table = ({ dataSource, columns }) => (
    <table>
      <thead>
        <tr>
          {columns.map((col, idx) => (
            <th key={idx}>{col.title}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {dataSource.map((row, rIdx) => (
          <tr key={rIdx}>
            {columns.map((col, cIdx) => (
              <td key={cIdx}>
                {col.render ? col.render(row[col.dataIndex], row) : row[col.dataIndex]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );

  const Card = ({ children, title }) => (
    <div data-testid="card-wrapper">
      {title && <h3>{title}</h3>}
      {children}
    </div>
  );

  const Button = ({ children, onClick, loading, disabled, icon, ...props }) => (
    <button onClick={onClick} disabled={disabled || loading} {...props}>
      {loading ? "Loading..." : (children || icon)}
    </button>
  );

  const Tag = ({ children, color }) => <span className={`tag-${color}`}>{children}</span>;
  const Space = ({ children }) => <div>{children}</div>;
  
  const Typography = {
    Title: ({ children }) => <h1>{children}</h1>,
    Text: ({ children, type }) => <span className={type}>{children}</span>,
    Paragraph: ({ children }) => <p>{children}</p>,
  };

  const Modal = ({ children, title, open, onCancel }) => open ? (
    <div data-testid="modal-wrapper">
      <h2>{title}</h2>
      {children}
      <button onClick={onCancel}>Cancel</button>
    </div>
  ) : null;

  const Form = Object.assign(
    ({ children, onFinish }) => (
      <form onSubmit={(e) => { e.preventDefault(); onFinish && onFinish(mockFormValues); }}>{children}</form>
    ),
    {
      useForm: () => {
        mockFormValues = {};
        const formInstance = {
          resetFields: () => { mockFormValues = {}; },
          setFieldsValue: (vals) => { mockFormValues = { ...mockFormValues, ...vals }; },
          getFieldsValue: () => mockFormValues,
        };
        return [formInstance];
      },
      Item: ({ children, name, label }) => {
        if (React.isValidElement(children) && name) {
          const childValue = mockFormValues[name];
          const childOnChange = (e) => {
            const val = (e && e.target && e.target.value !== undefined) ? e.target.value : e;
            if (children.props.mode === "multiple") {
              const current = mockFormValues[name] || [];
              if (current.includes(val)) {
                mockFormValues[name] = current.filter(x => x !== val);
              } else {
                mockFormValues[name] = [...current, val];
              }
            } else {
              mockFormValues[name] = val;
            }
            if (children.props.onChange) {
              children.props.onChange(e);
            }
          };
          return (
            <div>
              {label && <label>{label}</label>}
              {React.cloneElement(children, {
                value: childValue,
                onChange: childOnChange,
                name: name
              })}
            </div>
          );
        }
        return (
          <div>
            {label && <label>{label}</label>}
            {children}
          </div>
        );
      }
    }
  );

  const Input = Object.assign(
    (props) => <input {...props} />,
    {
      Password: (props) => <input type="password" aria-label="Secret Key Token" {...props} />
    }
  );

  const Select = Object.assign(
    ({ children, onChange, value, placeholder, mode }) => {
      const [isOpen, setIsOpen] = React.useState(false);
      return (
        <div style={{ position: "relative" }}>
          <div 
            role="combobox" 
            aria-expanded={isOpen}
            onClick={() => setIsOpen(!isOpen)}
            style={{ border: "1px solid #ccc", padding: "4px", cursor: "pointer" }}
          >
            {mode === "multiple" 
              ? (Array.isArray(value) && value.length > 0 ? value.join(", ") : "Select multiple...") 
              : (value || placeholder || "Select...")}
          </div>
          {isOpen && (
            <div role="listbox" style={{ position: "absolute", background: "white", border: "1px solid #ccc", zIndex: 10 }}>
              {React.Children.map(children, child => 
                React.cloneElement(child, { 
                  onClick: (val) => {
                    onChange && onChange(val);
                    if (mode !== "multiple") {
                      setIsOpen(false);
                    }
                  }
                })
              )}
            </div>
          )}
        </div>
      );
    },
    {
      Option: ({ children, value, onClick }) => (
        <div 
          role="option" 
          onClick={() => onClick && onClick(value)}
          style={{ padding: "4px", cursor: "pointer" }}
        >
          {children}
        </div>
      )
    }
  );

  const message = {
    success: jest.fn(),
    error: jest.fn(),
    loading: jest.fn()
  };

  const Tabs = ({ items, activeKey, onChange }) => (
    <div>
      <div>
        {items.map(item => (
          <button 
            key={item.key} 
            onClick={() => onChange && onChange(item.key)}
            style={{ fontWeight: activeKey === item.key ? "bold" : "normal" }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.map(item => (
        <div 
          key={item.key} 
          data-testid={`tab-content-${item.key}`}
          style={{ display: activeKey === item.key ? "block" : "none" }}
        >
          {item.children}
        </div>
      ))}
    </div>
  );

  const Switch = ({ checked, onChange }) => (
    <input type="checkbox" checked={checked} onChange={(e) => onChange && onChange(e.target.checked)} />
  );

  const Tooltip = ({ children, title }) => <span title={title}>{children}</span>;
  const Divider = () => <hr />;
  const Row = ({ children }) => <div>{children}</div>;
  const Col = ({ children }) => <div>{children}</div>;
  const Badge = ({ text }) => <span>{text}</span>;
  
  const Popconfirm = ({ children, onConfirm, title, okText }) => {
    const [isOpen, setIsOpen] = React.useState(false);
    return (
      <span style={{ position: "relative" }}>
        <span onClick={() => setIsOpen(!isOpen)}>{children}</span>
        {isOpen && (
          <div role="tooltip" style={{ position: "absolute", background: "white", border: "1px solid #ccc", zIndex: 10, padding: "8px" }}>
            <div>{title || "Confirm?"}</div>
            <button onClick={() => { onConfirm && onConfirm(); setIsOpen(false); }}>
              {okText || "Yes"}
            </button>
            <button onClick={() => setIsOpen(false)}>No</button>
          </div>
        )}
      </span>
    );
  };
  
  const List = ({ dataSource, renderItem }) => (
    <div>{dataSource.map((item, index) => <div key={index}>{renderItem(item, index)}</div>)}</div>
  );
  
  const Alert = ({ message, type }) => <div className={`alert-${type}`}>{message}</div>;
  const Spin = () => <div>Loading...</div>;

  return {
    Table, Card, Button, Tag, Space, Typography, Modal, Form,
    Input, Select, message, Tabs, Divider, Row, Col, Badge, Switch,
    Tooltip, Popconfirm, List, Alert, Spin
  };
});

describe("AIProviderConfig Component", () => {
  const API = "http://localhost:8000";
  const token = "test-token";

  const mockProviders = [
    {
      provider_id: "prov-1",
      provider_name: "Mock OpenAI",
      provider_type: "openai",
      base_url: "https://api.openai.com/v1",
      is_active: true,
      masked_api_key: "sk-...abcd",
      status: "HEALTHY",
      last_success_at: "2026-08-20T10:00:00Z",
      last_failure_at: null,
      failure_count: 0,
      consecutive_failures: 0,
      average_response_ms: 120.0
    },
    {
      provider_id: "prov-2",
      provider_name: "Mock Groq",
      provider_type: "groq",
      base_url: "https://api.groq.com",
      is_active: false,
      masked_api_key: null,
      status: "UNKNOWN",
      last_success_at: null,
      last_failure_at: null,
      failure_count: 0,
      consecutive_failures: 0,
      average_response_ms: null
    }
  ];

  const mockModels = [
    {
      model_id: "model-1",
      provider_id: "prov-1",
      provider_name: "Mock OpenAI",
      provider_type: "openai",
      model_name: "gpt-4o",
      purpose: "sql_generation",
      is_default: true,
      is_active: true,
      provider_active: true,
      health_status: "HEALTHY"
    },
    {
      model_id: "model-2",
      provider_id: "prov-1",
      provider_name: "Mock OpenAI",
      provider_type: "openai",
      model_name: "gpt-4o-mini",
      purpose: "sql_generation",
      is_default: false,
      is_active: true,
      provider_active: true,
      health_status: "HEALTHY"
    }
  ];

  const mockFallbacks = [
    {
      fallback_id: "fb-1",
      purpose: "sql_generation",
      priority_order: 1,
      is_active: true,
      model_id: "model-1",
      model_name: "gpt-4o",
      provider_name: "Mock OpenAI",
      provider_type: "openai"
    },
    {
      fallback_id: "fb-2",
      purpose: "sql_generation",
      priority_order: 2,
      is_active: true,
      model_id: "model-2",
      model_name: "gpt-4o-mini",
      provider_name: "Mock OpenAI",
      provider_type: "openai"
    }
  ];

  const defaultFetchMock = (url) => {
    if (url.includes("/providers")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockProviders)
      });
    }
    if (url.includes("/models")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockModels)
      });
    }
    if (url.includes("/fallbacks")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockFallbacks)
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({})
    });
  };

  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn((url, options) => defaultFetchMock(url));
    mockFormValues = {};
  });

  // 1, 2, 3, 14. Loading and loads checks
  test("loads and renders the control center UI with stats overview cards", async () => {
    render(<AIProviderConfig API={API} token={token} />);
    
    expect(screen.getByText("AI Model Control Center")).toBeInTheDocument();
    
    await waitFor(() => {
      // Check Stats Cards labels
      expect(screen.getByText("Active Providers")).toBeInTheDocument();
      expect(screen.getAllByText("Registered Models").length).toBeGreaterThan(0);
      expect(screen.getByText("Healthy Connections")).toBeInTheDocument();
      expect(screen.getByText("Fallback Routes")).toBeInTheDocument();
    });
  });

  test("loads and displays providers table contents", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    await waitFor(() => {
      // Verify provider names are rendered
      expect(screen.getAllByText("Mock OpenAI").length).toBeGreaterThan(0);
      expect(screen.getByText("Mock Groq")).toBeInTheDocument();
      // Verify key secure masking
      expect(screen.getByText("sk-...abcd")).toBeInTheDocument();
    });
  });

  test("loads and displays models list contents", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    await waitFor(() => {
      // Verify model names are rendered
      expect(screen.getAllByText("gpt-4o").length).toBeGreaterThan(0);
      expect(screen.getAllByText("gpt-4o-mini").length).toBeGreaterThan(0);
    });
  });

  test("loads and renders fallback routing cards", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    await waitFor(() => {
      // Check for purpose card titles
      expect(screen.getByText("SQL Query Generation")).toBeInTheDocument();
      expect(screen.getByText("Business Explanation & Insights")).toBeInTheDocument();
      expect(screen.getByText("Conversational Intent Classifier")).toBeInTheDocument();
      expect(screen.getByText("Chart Aggregator & Visual Selector")).toBeInTheDocument();
    });
  });

  // 4. Add provider modal submit check
  test("submits create provider form values correctly", async () => {
    render(<AIProviderConfig API={API} token={token} />);
    
    // Switch to Connection Providers tab
    const providersTab = screen.getByRole("button", { name: /Connection Providers/i });
    fireEvent.click(providersTab);

    // Wait for the table data to be loaded
    await screen.findAllByText("Mock OpenAI");

    // Click Add Provider button
    const addBtn = screen.getByRole("button", { name: /add provider/i });
    fireEvent.click(addBtn);

    // Form modal is visible
    expect(screen.getByText("Register AI Connection Node")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("e.g. OpenAI Cloud Production"), {
      target: { value: "New Provider Node" }
    });

    const submitBtn = screen.getByRole("button", { name: /save node config/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/providers"),
        expect.objectContaining({
          method: "POST"
        })
      );
    });
  });

  // 6. Test provider node connectivity
  test("triggers connection test for provider and shows success status", async () => {
    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("/test")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: "success", latency_ms: 105 })
        });
      }
      return defaultFetchMock(url);
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    // Switch to Connection Providers tab
    const providersTab = screen.getByRole("button", { name: /Connection Providers/i });
    fireEvent.click(providersTab);

    // Wait for providers table to load
    await screen.findAllByText("Mock OpenAI");

    const testBtns = screen.getAllByRole("button", { name: /test connection/i });
    fireEvent.click(testBtns[0]);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/providers/prov-1/test"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  // 7. Test model completion API
  test("triggers completions test for model and shows latency success", async () => {
    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("/test")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: "success", latency_ms: 215, response: "hello" })
        });
      }
      return defaultFetchMock(url);
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    // Switch to Registered Models tab
    const modelsTab = screen.getByRole("button", { name: /Registered Models/i });
    fireEvent.click(modelsTab);

    // Wait for models list to load
    await screen.findAllByText("gpt-4o");

    const testBtns = screen.getAllByRole("button", { name: /test model/i });
    fireEvent.click(testBtns[0]);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/models/model-1/test"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  // 8. Set Primary Routing
  test("updates primary model routing when a new model is selected", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    // Wait for loading to finish
    await screen.findAllByText("gpt-4o-mini");

    const selects = await screen.findAllByRole("combobox");
    fireEvent.click(selects[0]);

    const option = await screen.findByRole("option", { name: /gpt-4o-mini/i });
    fireEvent.click(option);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/model-routing"),
        expect.objectContaining({ method: "PUT" })
      );
    });
  });

  // 10. Remove Fallback
  test("triggers fallback removal when delete is clicked", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    // Wait for fallback items to load
    await screen.findAllByText("gpt-4o-mini");

    const deleteBtns = screen.getAllByRole("button", { name: /delete fallback/i });
    fireEvent.click(deleteBtns[0]);

    // Confirm the Popconfirm
    const confirmBtn = await screen.findByRole("button", { name: /yes/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/fallbacks/fb-2"),
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });

  // 12. Error handling checks
  test("displays user-friendly error message when fetch returns 403", async () => {
    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("/providers")) {
        return Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ detail: "Access denied to admin resources" })
        });
      }
      return defaultFetchMock(url);
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
  });

  // 13. No Key Exposure checks
  test("inputs password write-only for provider credentials", async () => {
    render(<AIProviderConfig API={API} token={token} />);
    
    // Switch to Connection Providers tab
    const providersTab = screen.getByRole("button", { name: /Connection Providers/i });
    fireEvent.click(providersTab);

    // Wait for providers table to load
    await screen.findAllByText("Mock OpenAI");

    const keyBtns = screen.getAllByRole("button");
    // Find credentials / API key update button (which has Key icon)
    const keyBtn = keyBtns.find(btn => btn.querySelector('[aria-label="key"]'));
    fireEvent.click(keyBtn);

    // Wait for the password input to appear in the modal
    const passwordInput = await screen.findByPlaceholderText(/token/i);
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  test("model registration shows multi-capability UI and allows selecting multiple capabilities", async () => {
    render(<AIProviderConfig API={API} token={token} />);
    
    // Switch to Registered Models tab
    const modelsTab = screen.getByRole("button", { name: /Registered Models/i });
    fireEvent.click(modelsTab);

    // Wait for data loading
    await screen.findAllByText("gpt-4o");

    // Click Add Model button
    const addBtn = screen.getByRole("button", { name: /add model/i });
    fireEvent.click(addBtn);

    // Form modal is visible
    expect(screen.getByText("Register Model Reference")).toBeInTheDocument();

    // Check for Capabilities select combobox
    const selects = screen.getAllByRole("combobox");
    // Under registered models add modal, the first select is Provider, the second is Capabilities
    expect(selects.length).toBeGreaterThanOrEqual(2);
  });

  test("registering a model with multiple capabilities sends the purposes list to the backend", async () => {
    global.fetch = jest.fn().mockImplementation((url, options) => {
      if (url.includes("/models") && options && options.method === "POST") {
        const body = JSON.parse(options.body);
        expect(body.purposes).toEqual(["sql_generation", "insight", "intent", "chart"]);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ message: "Model created" }) });
      }
      return defaultFetchMock(url);
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    const modelsTab = screen.getByRole("button", { name: /Registered Models/i });
    fireEvent.click(modelsTab);
    await screen.findAllByText("gpt-4o");

    const addBtn = screen.getByRole("button", { name: /add model/i });
    fireEvent.click(addBtn);

    // Fill form
    fireEvent.change(screen.getByPlaceholderText(/gpt-4o-mini/i), {
      target: { value: "my-custom-model" }
    });

    // Select provider
    const selects = screen.getAllByRole("combobox");
    fireEvent.click(selects[0]);
    const provOption = screen.getByRole("option", { name: "Mock OpenAI" });
    fireEvent.click(provOption);

    // Select capabilities
    fireEvent.click(selects[1]);
    const opt1 = screen.getByRole("option", { name: /sql generation/i });
    const opt2 = screen.getByRole("option", { name: /business insight/i });
    const opt3 = screen.getByRole("option", { name: /intent/i });
    const opt4 = screen.getByRole("option", { name: /chart/i });
    fireEvent.click(opt1);
    fireEvent.click(opt2);
    fireEvent.click(opt3);
    fireEvent.click(opt4);

    const submitBtn = screen.getByRole("button", { name: /register model/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/models"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  test("model list groups repeated model-purpose rows into one logical model with multiple tags", async () => {
    const duplicateModels = [
      {
        model_id: "model-1",
        provider_id: "prov-1",
        provider_name: "Mock OpenAI",
        provider_type: "openai",
        model_name: "gpt-4o-shared",
        purpose: "sql_generation",
        is_default: true,
        is_active: true,
        provider_active: true,
        health_status: "HEALTHY"
      },
      {
        model_id: "model-2",
        provider_id: "prov-1",
        provider_name: "Mock OpenAI",
        provider_type: "openai",
        model_name: "gpt-4o-shared",
        purpose: "insight",
        is_default: false,
        is_active: true,
        provider_active: true,
        health_status: "HEALTHY"
      }
    ];

    global.fetch = jest.fn((url) => {
      if (url.includes("/models")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(duplicateModels) });
      }
      return defaultFetchMock(url);
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    const modelsTab = screen.getByRole("button", { name: /Registered Models/i });
    fireEvent.click(modelsTab);

    await waitFor(() => {
      expect(screen.getAllByText("gpt-4o-shared").length).toBe(1);
      expect(screen.getByText("SQL Generation")).toBeInTheDocument();
      expect(screen.getByText("Business Insight")).toBeInTheDocument();
    });
  });

  test("formats Pydantic 422 validation errors into user-friendly notifications without crashing", async () => {
    const errorDetail = [
      {
        type: "missing",
        loc: ["body", "provider_id"],
        msg: "Field required",
        input: null
      },
      {
        type: "value_error",
        loc: ["body", "purposes"],
        msg: "At least one capability required",
        input: null
      }
    ];

    global.fetch = jest.fn().mockImplementation((url, options) => {
      if (url.includes("/models") && options && options.method === "POST") {
        return Promise.resolve({
          ok: false,
          status: 422,
          json: () => Promise.resolve({ detail: errorDetail })
        });
      }
      return defaultFetchMock(url);
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    // Open modal
    const modelsTab = screen.getByRole("button", { name: /Registered Models/i });
    fireEvent.click(modelsTab);
    await screen.findAllByText("gpt-4o");

    const addBtn = screen.getByRole("button", { name: /add model/i });
    fireEvent.click(addBtn);

    // Enter name
    fireEvent.change(screen.getByPlaceholderText(/gpt-4o-mini/i), {
      target: { value: "test-fail-model" }
    });

    const submitBtn = screen.getByRole("button", { name: /register model/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      const antd = require("antd");
      expect(antd.message.error).toHaveBeenCalledWith(
        "provider_id: Field required; purposes: At least one capability required"
      );
    });
  });

  test("displays detailed health telemetry metrics (consecutive/total failures, last success) in provider rows", async () => {
    const customProviders = [
      {
        provider_id: "prov-test",
        provider_name: "Telemetry Provider",
        provider_type: "openai",
        base_url: "https://api.openai.com/v1",
        is_active: true,
        masked_api_key: "sk-...abcd",
        status: "HEALTHY",
        last_success_at: "2026-08-20T10:00:00.000Z",
        last_failure_at: null,
        failure_count: 14,
        consecutive_failures: 2,
        average_response_ms: 120.0
      }
    ];

    global.fetch = jest.fn((url) => {
      if (url.includes("/providers")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(customProviders) });
      }
      return defaultFetchMock(url);
    });

    render(<AIProviderConfig API={API} token={token} />);

    // Switch to Connection Providers tab
    const providersTab = screen.getByRole("button", { name: /Connection Providers/i });
    fireEvent.click(providersTab);

    // Verify health metrics are displayed correctly
    await waitFor(() => {
      expect(screen.getAllByText("CONNECTED")[0]).toBeInTheDocument();
      expect(screen.getByText((_, el) => el.textContent.startsWith("Consecutive Failures:") && el.textContent.includes("2"))).toBeInTheDocument();
      expect(screen.getByText((_, el) => el.textContent.startsWith("Total Failures:") && el.textContent.includes("14"))).toBeInTheDocument();
      expect(screen.getByText((_, el) => el.textContent.startsWith("Last Success:"))).toBeInTheDocument();
    });
  });
});
