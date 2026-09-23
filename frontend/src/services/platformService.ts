import apiClient from '../api/apiClient'
import { ApiRoutes } from '../api/routes'

export interface PlatformMetadata {
  name: string
  version: string
}

/**
 * Fetch canonical platform metadata from the public /version endpoint.
 */
export const getPlatformMetadata = async (): Promise<PlatformMetadata> => {
  const response = await apiClient.get<PlatformMetadata>(ApiRoutes.platform.version, {
    baseURL: '',
  })
  return response.data
}
