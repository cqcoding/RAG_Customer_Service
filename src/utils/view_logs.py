#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime

LOG_DIR = Path("./logs")

def view_llm_logs():
    """Visualiza logs de chamadas LLM."""
    llm_log = LOG_DIR / "llm_calls.jsonl"
    
    if not llm_log.exists():
        print("Nenhum log LLM encontrado.")
        return
    
    print("\n" + "="*80)
    print("LOGS DE CHAMADAS LLM")
    print("="*80 + "\n")
    
    with open(llm_log) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event_type") != "llm_call":
                    continue
                print(f"[{entry['timestamp']}] {entry['provider']} - {entry['model']}")
                print(f"  Agent: {entry.get('agent', 'N/A')}")
                print(f"  Status: {entry['status']}")
                print(f"  Latência: {entry['latency_ms']}ms")
                print(f"  Prompt (primeiros chars): {entry['prompt'][:100]}...")
                print(f"  Response (primeiros chars): {entry['response'][:100]}...")
                print()
            except json.JSONDecodeError:
                continue

def view_agent_logs():
    """Visualiza logs de execução de agentes."""
    trace_log = LOG_DIR / "trace.log"
    
    if not trace_log.exists():
        print("Nenhum log de trace encontrado.")
        return
    
    print("\n" + "="*80)
    print("LOGS DE EXECUÇÃO DE AGENTES")
    print("="*80 + "\n")
    
    with open(trace_log) as f:
        for line in f:
            if "agent_execution" in line:
                print(line)

def view_routing_logs():
    """Visualiza decisões de roteamento."""
    llm_log = LOG_DIR / "llm_calls.jsonl"
    
    if not llm_log.exists():
        print("Nenhum log encontrado.")
        return
    
    print("\n" + "="*80)
    print("DECISÕES DE ROTEAMENTO")
    print("="*80 + "\n")
    
    with open(llm_log) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event_type") == "routing_decision":
                    print(f"[{entry['timestamp']}]")
                    print(f"  Query: {entry['user_query']}")
                    print(f"  Agentes selecionados: {', '.join(entry['agents_selected'])}")
                    print(f"  Total de agentes: {entry['num_agents']}")
                    print()
            except json.JSONDecodeError:
                continue

def stats():
    """Exibe estatísticas dos logs."""
    llm_log = LOG_DIR / "llm_calls.jsonl"
    
    if not llm_log.exists():
        print("Nenhum log encontrado.")
        return
    
    print("\n" + "="*80)
    print("ESTATÍSTICAS")
    print("="*80 + "\n")
    
    total_calls = 0
    total_latency = 0
    by_agent = {}
    
    with open(llm_log) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event_type") == "llm_call":
                    total_calls += 1
                    total_latency += entry['latency_ms']
                    agent = entry.get('agent', 'unknown')
                    by_agent[agent] = by_agent.get(agent, 0) + 1
            except json.JSONDecodeError:
                continue
    
    print(f"Total de chamadas LLM: {total_calls}")
    print(f"Latência média: {total_latency / total_calls:.2f}ms" if total_calls > 0 else "N/A")
    print(f"\nChamadas por agente:")
    for agent, count in sorted(by_agent.items()):
        print(f"  {agent}: {count}")

if __name__ == "__main__":
    print("RAG Logs Viewer")
    print("\nOpções:")
    print("1. Visualizar logs de chamadas LLM")
    print("2. Visualizar execução de agentes")
    print("3. Visualizar decisões de roteamento")
    print("4. Visualizar estatísticas")
    print("5. Visualizar todos os logs e estatísticas")
    
    choice = input("\nEscolha uma opção (1-5): ").strip()
    
    if choice == "1":
        view_llm_logs()
    elif choice == "2":
        view_agent_logs()
    elif choice == "3":
        view_routing_logs()
    elif choice == "4":
        stats()
    elif choice == "5":
        view_routing_logs()
        view_llm_logs()
        view_agent_logs()
        stats()
    else:
        print("Opção inválida.")
