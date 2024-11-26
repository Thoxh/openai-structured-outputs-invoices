'use client'

import { useState, useRef } from 'react'
import Image from 'next/image'
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AlertCircle, CheckCircle, Loader2, Upload } from 'lucide-react'

const SYSTEM_MESSAGES = {
  INVOICE_UPLOAD: "Du bist ein Assistent, der Rechnungsdaten extrahiert.",
  DATABASE_QUERY: "Du bist ein Assistent für Datenbankabfragen."
}

export default function PDFInvoiceUpload() {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [response, setResponse] = useState<string | null>(null)
  const [queryText, setQueryText] = useState('')
  const [queryResponse, setQueryResponse] = useState<string | null>(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      setFile(event.target.files[0])
    }
  }

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
  }

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (event.dataTransfer.files && event.dataTransfer.files[0]) {
      setFile(event.dataTransfer.files[0])
    }
  }

  const handleUpload = async () => {
    if (!file) return

    setUploading(true)
    setUploadProgress(0)
    setResponse(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('system_message', SYSTEM_MESSAGES.INVOICE_UPLOAD)

    try {
      const response = await fetch('http://127.0.0.1:5002/upload', {
        method: 'POST',
        body: formData,
      })

      if (response.ok) {
        const result = await response.json()
        setResponse(JSON.stringify(result, null, 2))
      } else {
        setResponse('Upload failed')
      }
    } catch (error) {
      setResponse('Error: ' + (error as Error).message)
    } finally {
      setUploading(false)
      setUploadProgress(100)
    }
  }

  const handleQuerySubmit = async () => {
    setQueryResponse(null)
    setQueryLoading(true)

    try {
      const response = await fetch('http://127.0.0.1:5002/process', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: queryText,
          system_message: SYSTEM_MESSAGES.DATABASE_QUERY
        }),
      })

      if (response.ok) {
        const result = await response.json()
        setQueryResponse(JSON.stringify(result, null, 2))
      } else {
        setQueryResponse('Query failed')
      }
    } catch (error) {
      setQueryResponse('Error: ' + (error as Error).message)
    } finally {
      setQueryLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-6">
          <div className="flex justify-center">
            <Image
              src="https://hebbkx1anhila5yf.public.blob.vercel-storage.com/Technische_Hochschule_Brandenburg_Logo.svg-yJa7AHSax1OpkUTnWn3Zya2dZhjJWU.png"
              alt="Technische Hochschule Brandenburg Logo"
              width={200}
              height={53}
              priority
            />
          </div>
          <CardTitle className="text-2xl font-bold text-center">Rechnungsverwaltung</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="upload" className="space-y-6">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="upload">Rechnung hochladen</TabsTrigger>
              <TabsTrigger value="query">Abfragen</TabsTrigger>
            </TabsList>
            <TabsContent value="upload" className="space-y-6">
              <div
                className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <Input
                  type="file"
                  accept=".pdf"
                  onChange={handleFileChange}
                  ref={fileInputRef}
                  className="hidden"
                />
                <Upload className="mx-auto h-12 w-12 text-gray-400" />
                <p className="mt-4 text-sm text-gray-500">
                  Klicken Sie hier oder ziehen Sie eine Datei in diesen Bereich, um sie hochzuladen
                </p>
                <p className="mt-2 text-xs text-gray-500">PDF (max. 10MB)</p>
              </div>
              {file && (
                <div className="flex items-center space-x-2">
                  <CheckCircle className="text-green-500 h-5 w-5" />
                  <span className="text-sm text-gray-500">{file.name}</span>
                </div>
              )}
              <Button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="w-full"
              >
                {uploading ? (
                  <div className="flex items-center justify-center">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Wird hochgeladen...
                  </div>
                ) : (
                  'Hochladen'
                )}
              </Button>
              {uploading && (
                <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
                  <div
                    className="bg-primary h-2.5 rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${uploadProgress}%` }}
                  ></div>
                </div>
              )}
              {response && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Antwort</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="bg-gray-100 p-2 rounded text-sm overflow-x-auto">
                      {response}
                    </pre>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
            <TabsContent value="query" className="space-y-6">
              <div className="space-y-4">
                <Input
                  type="text"
                  placeholder="Geben Sie Ihre Abfrage ein..."
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                />
                <Button onClick={handleQuerySubmit} disabled={queryLoading} className="w-full">
                  {queryLoading ? (
                    <div className="flex items-center justify-center">
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Abfrage wird verarbeitet...
                    </div>
                  ) : (
                    'Abfrage senden'
                  )}
                </Button>
              </div>
              {queryResponse && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Abfrageergebnis</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="bg-gray-100 p-2 rounded text-sm overflow-x-auto">
                      {queryResponse}
                    </pre>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}