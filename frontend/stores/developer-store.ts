import { create } from "zustand"
import { apiClient } from "@/lib/api-client"
import type {
  Application,
  CreateApplicationRequest,
  ApplicationAPIKey,
  CreateApplicationKeyRequest,
  AgentSchema,
  CreateSchemaRequest,
  SchemaVersion,
  AgentAPIConfig,
  ConfigureAgentAPIRequest,
} from "@/types/playground"

interface DeveloperState {
  applications: Application[]
  selectedAppKeys: ApplicationAPIKey[]
  schemas: AgentSchema[]
  isLoading: boolean
  oneTimeSecret: string | null

  fetchApplications: () => Promise<void>
  createApplication: (data: CreateApplicationRequest) => Promise<Application>
  fetchApplicationKeys: (appId: string) => Promise<void>
  createApplicationKey: (appId: string, data: CreateApplicationKeyRequest) => Promise<string>
  revokeApplicationKey: (appId: string, keyId: string) => Promise<void>
  clearOneTimeSecret: () => void

  fetchSchemas: () => Promise<void>
  createSchema: (data: CreateSchemaRequest) => Promise<AgentSchema>
  createSchemaVersion: (schemaId: string, data: CreateSchemaRequest) => Promise<SchemaVersion>
  validateSchemaPayload: (schemaId: string, versionId: string, payload: object) => Promise<{ valid: boolean; errors: any[] }>

  configureAgentAPI: (agentId: string, data: ConfigureAgentAPIRequest) => Promise<AgentAPIConfig>
  publishAgentAPI: (agentId: string) => Promise<{ agent_id: string; agent_version: number; publication_state: string }>
  transitionAgentAPI: (agentId: string, action: string) => Promise<{ agent_id: string; publication_state: string }>
}

export const useDeveloperStore = create<DeveloperState>((set, get) => ({
  applications: [],
  selectedAppKeys: [],
  schemas: [],
  isLoading: false,
  oneTimeSecret: null,

  fetchApplications: async () => {
    set({ isLoading: true })
    try {
      const applications = await apiClient.listApplications()
      set({ applications, isLoading: false })
    } catch (error) {
      console.error("Failed to fetch applications:", error)
      set({ isLoading: false })
    }
  },

  createApplication: async (data: CreateApplicationRequest) => {
    const app = await apiClient.createApplication(data)
    set((s) => ({ applications: [...s.applications, app] }))
    return app
  },

  fetchApplicationKeys: async (appId: string) => {
    try {
      const keys = await apiClient.listApplicationKeys(appId)
      set({ selectedAppKeys: keys })
    } catch (error) {
      console.error("Failed to fetch keys:", error)
    }
  },

  createApplicationKey: async (appId: string, data: CreateApplicationKeyRequest) => {
    const res = await apiClient.createApplicationKey(appId, data)
    set((s) => ({
      selectedAppKeys: [...s.selectedAppKeys, res],
      oneTimeSecret: res.api_key,
    }))
    return res.api_key
  },

  revokeApplicationKey: async (appId: string, keyId: string) => {
    const updated = await apiClient.revokeApplicationKey(appId, keyId)
    set((s) => ({
      selectedAppKeys: s.selectedAppKeys.map((k) => (k.id === keyId ? updated : k)),
    }))
  },

  clearOneTimeSecret: () => set({ oneTimeSecret: null }),

  fetchSchemas: async () => {
    set({ isLoading: true })
    try {
      const schemas = await apiClient.listSchemas()
      set({ schemas, isLoading: false })
    } catch (error) {
      console.error("Failed to fetch schemas:", error)
      set({ isLoading: false })
    }
  },

  createSchema: async (data: CreateSchemaRequest) => {
    const s = await apiClient.createSchema(data)
    set((state) => ({ schemas: [...state.schemas, s] }))
    return s
  },

  createSchemaVersion: async (schemaId: string, data: CreateSchemaRequest) => {
    const v = await apiClient.createSchemaVersion(schemaId, data)
    await get().fetchSchemas()
    return v
  },

  validateSchemaPayload: async (schemaId: string, versionId: string, payload: object) => {
    return apiClient.validateSchema(schemaId, versionId, payload)
  },

  configureAgentAPI: async (agentId: string, data: ConfigureAgentAPIRequest) => {
    return apiClient.configureAgentAPI(agentId, data)
  },

  publishAgentAPI: async (agentId: string) => {
    return apiClient.publishAgentAPI(agentId)
  },

  transitionAgentAPI: async (agentId: string, action: string) => {
    return apiClient.transitionAgentAPI(agentId, action)
  },
}))
