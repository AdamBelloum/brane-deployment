import streamlit as st

def render_home_dashboard():
    """Renders your original core hub system diagnostics view."""
    st.title("🌐 Brane Distributed Framework Console")
    
    with st.expander("📖 System Guide & Overview", expanded=True):
         col_a, col_b = st.columns(2)
         with col_a:
             st.markdown("""
             **What it does:** Serves as the central command hub monitoring the health and IP distribution of your distributed Brane cluster infrastructure.
             """)
         with col_b:
             st.markdown("""
             **Who is this for:** System Administrators, Developers, and Data Scientists.
             **Prerequisites:** Target infrastructure nodes must be active on your network layer.
             """)
             
    st.write("Welcome to the unified Brane management platform. Use the sidebar to deploy infrastructure, stage packages, or write computations.")
    st.divider()
    st.subheader("🖥️ Target Node Cluster Topology Status")
    
    col1, col2, col3 = st.columns(3)
    with col1:
         st.metric(label="Central Hub (hub-vm-1)", value="145.100.135.209", delta="Active")
         st.info("**Role**: Central Control, API Gateway, Orchestrator")
    with col2:
         st.metric(label="Worker Node 1 (worker-vm-2)", value="145.100.135.172", delta="Active")
         st.info("**Location ID**: client-node-1")
    with col3:
         st.metric(label="Worker Node 2 (worker-vm-3)", value="145.100.135.241", delta="Active")
         st.info("**Location ID**: client-node-2")
