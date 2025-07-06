"use client"

import LoginBackground from '../../background'
import Button from '@ui-library/Button'
import { useState } from 'react'
import 'react-phone-number-input/style.css'
import PhoneInput from 'react-phone-number-input'
import Link from 'next/link'
import { useTranslation } from '@hooks/useTranslation'
import { User } from '@app//types/general'
import { GitHub, Google } from '@lib/Logos'

const isUpperCase = new RegExp(/(?=.*[A-Z])/g)
const isSpecialChar = new RegExp(/(?=.*[!@#$%^&*,.])/g)
const isLowerCase = new RegExp(/(?=.*[a-z])/g)
const isLong = new RegExp(/(?=.{7,})/g)
const isNumeric = new RegExp(/(?=.*[0-9])/g)
const checkIsWhiteSpace = new RegExp(/^[^ ]/g)
const isValidEmail = new RegExp(/^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/);

export default function Page() {
  const [t] = useTranslation();
  const [user, setUser] = useState<User>({
    id : 0
  })

  const [errorName, setErrorName] = useState<string| null>(null)
  const [errorLastName, setErrorLastName] = useState<string| null>(null)
  // const [errorUserName, setErrorUserName] = useState<string| null>(null)
  const [errorBirthdate, setErrorBirthdate] = useState<string| null>(null)

  const [errorPass, setErrorPass] = useState<string| null>(null)
  const [errorEmail, setErrorEmail] = useState<string| null>(null)
  const [errorPhone, setErrorPhone] = useState<string| null>(null)
  const [errorPolicy, setErrorPolicy] = useState<string| null>(null)

  const [polityCheck, setPolityCheck] = useState<boolean>(false)

  const doesContainYourName = (pass:string, user: User) => {
    if(user.name && pass.includes(user.name))
      return true
    if(user.last_name && pass.includes(user.last_name))
      return true
    return false
  }

  const validatePass = (): string| boolean => {

    const pass = user.password && user.password.length > 0 ? user.password: '';

    // password check
    if(pass === '')
      setErrorPass( "Please enter a valid password")
    if(!pass.match(isUpperCase))
      setErrorPass( "Password must have at least 1 Capital letter")
    if(!pass.match(isSpecialChar))
      setErrorPass("Password must contain at least 1 special character")
    if(!pass.match(isLowerCase))
      setErrorPass( "Password must have at least 1 Lower case letter")
    if(!pass.match(isLong))
      setErrorPass("Password must contain at least 7 characters")
    if(!pass.match(isNumeric))
      setErrorPass("Password must have at least 1 numeric value")
    if(!pass.match(checkIsWhiteSpace))
      setErrorPass("Password must not have any white space")
    if(doesContainYourName(pass,user))
      setErrorPass("Do not use your name nor last name in the pass")

    return errorPass?.length == 0 
  }

  const SaveUser = () => {
    // e.preventDefault()

    if(!user.name || user.name === '')
      setErrorName("Name is mandatory")
    if(!user.last_name || user.last_name === '')
      setErrorLastName("Last Name is mandatory")

    if( user.phone == undefined || !user.phone || user.phone === '')
      setErrorPhone("Phone is mandatory")
    if(!user.birthDate || user.birthDate === '' || !(new Date(user.birthDate) instanceof Date))
      setErrorBirthdate("Birthday invalid")

    if(!user.email || user.email === '')
      setErrorEmail("Email is mandatory")
    if(user.email && !user.email.match(isValidEmail))
      setErrorEmail("Email is invalid")

    if(!validatePass())

    if(!polityCheck)
      setErrorPolicy("Must read policy and accept the terms")

    if(errorName != '' ||
      errorLastName != '' ||
      errorPhone != '' ||
      errorBirthdate != '' ||
      errorEmail != '' ||
      errorPass != '' ||
      errorPolicy != ''
     )
    return
  }

  return (
  <LoginBackground >
    <div className="container mx-auto px-4 h-full">
      <div className="flex content-center items-center justify-center h-full">
        <div className="w-full lg:w-6/12 px-4">
          <div className="relative flex flex-col min-w-0 break-words w-full mb-6 shadow-xl rounded-lg bg-blueGray-200 border-0">
            
            {/* External connections */}
            <div className="rounded-t mb-0 px-6 py-6">
              <div className="text-center mb-3">
                <h6 className="text-blueGray-500 text-sm font-bold">
                  Sign up with
                </h6>
              </div>
              <div className="btn-wrapper text-center">
                <button
                  className="bg-white active:bg-blueGray-50 text-blueGray-700 font-normal px-4 py-2 rounded outline-none focus:outline-none mr-2 mb-1 uppercase shadow hover:shadow-md inline-flex items-center font-bold text-xs ease-linear transition-all duration-150"
                  type="button"
                >
                  <GitHub height={20} width={20} />
                  <p className="ml-2">GitHub</p>
                </button>
                <button
                  className="bg-white active:bg-blueGray-50 text-blueGray-700 font-normal px-4 py-2 rounded outline-none focus:outline-none mr-1 mb-1 uppercase shadow hover:shadow-md inline-flex items-center font-bold text-xs ease-linear transition-all duration-150"
                  type="button"
                >
                  <Google height={20} width={20} />
                  <p className="ml-2">Google</p>
                </button>
              </div>
              <hr className="mt-6 border-b-1 border-blueGray-300" />
            </div>

            {/* User Form */}
            <div className="flex-auto px-4 lg:px-10 py-10 pt-0">
              <div className="text-blueGray-400 text-center mb-3 font-bold">
                <small>Or sign up with credentials</small>
              </div>
                {/* Name and LastName */}
                <div className="w-full mb-3 flex flex-nowrap">
                  <div className="w-full md:w-1/2 p-2"> 
                    <label
                      className="block text-blueGray-600 text-xs font-bold mb-2"
                      htmlFor="grid-password"
                    >
                      Name
                    </label>
                    <input
                      type="email"
                      className="border-0 px-3 py-3 placeholder-blueGray-300 text-blueGray-600 bg-white rounded text-sm shadow focus:outline-none focus:ring w-full ease-linear transition-all duration-150"
                      placeholder="Name"
                      onChange={(e) => {
                        setErrorName('')
                        setUser(prev => ({ ...prev, name: e.target.value }))
                      }}
                    />

                    {errorName && <label
                      className="block uppercase text-red-600 mt-2 text-xs font-bold mb-2"
                      htmlFor="grid-password"
                    >
                      {errorName}
                    </label>}
                  </div>
                  <div className="w-full md:w-1/2 p-2"> 
                    <label
                      className="block text-blueGray-600 text-xs font-bold mb-2"
                      htmlFor="grid-password"
                    >
                      Last Name
                    </label>
                    <input
                      type="email"
                      className="border-0 px-3 py-3 placeholder-blueGray-300 text-blueGray-600 bg-white rounded text-sm shadow focus:outline-none focus:ring w-full ease-linear transition-all duration-150"
                      placeholder="Last Name"
                      onChange={(e) =>{
                        setErrorLastName('')
                        setUser(prev => ({ ...prev, last_name: e.target.value }))
                      }}
                    />

                    {errorLastName && <label
                      className="block uppercase text-red-600 mt-2 text-xs font-bold mb-2"
                      htmlFor="grid-password"
                    >
                      {errorLastName}
                    </label>}
                  </div>

                </div>

                {/* Phone and Birthdate */}
                <div className="w-full mb-3 flex flex-nowrap">
                  <div className="w-full md:w-1/2 p-2">
                    <label className="block text-blueGray-600 text-xs font-bold mb-2">
                      Phone
                    </label>
                    <PhoneInput
                      className="border-0 px-3 py-3 placeholder-blueGray-300 text-blueGray-600 bg-white rounded text-sm shadow focus:outline-none focus:ring w-full ease-linear transition-all duration-150"
                      type="tel"
                      placeholder="Phone Number"
                      onChange={(e) => {
                        setErrorPhone('');
                        setUser(prev => ({ ...prev, phone: e?.toString()}))
                      }}
                    />
                    {errorPhone && <label
                      className="block uppercase text-red-600 mt-2 text-xs font-bold mb-2"
                      htmlFor="grid-password"
                    >
                      {errorPhone}
                    </label>}
                  </div>
                  <div className="w-full md:w-1/2 p-2">
                    <label className="block text-blueGray-600 text-xs font-bold mb-2">
                      Birthdate
                    </label>
                    <input
                      type="date"
                      className="border-0 px-3 py-3 placeholder-blueGray-300 text-blueGray-600 bg-white rounded text-sm shadow focus:outline-none focus:ring w-full ease-linear transition-all duration-150"
                      onChange={ (e) =>{
                        setErrorBirthdate('');
                        setUser(prev =>({ ...prev, birthDate: e.target.value }))
                      }}
                    />
                    {errorBirthdate && <label
                      className="block uppercase text-red-600 mt-2 text-xs font-bold mb-2"
                      htmlFor="grid-password"
                    >
                      {errorBirthdate}
                    </label>}
                  </div>
                </div>
          
                {/* Email */}
                <div className="relative w-full mb-3">
                  <label
                    className="block text-blueGray-600 text-xs font-bold mb-2"
                    htmlFor="grid-password"
                  >
                    Email
                  </label>
                  <input
                    type="email"
                    className="border-0 px-3 py-3 placeholder-blueGray-300 text-blueGray-600 bg-white rounded text-sm shadow focus:outline-none focus:ring w-full ease-linear transition-all duration-150"
                    onChange={(e) => { 
                      setErrorEmail(''); 
                      setUser(prev => ({ ...prev, email: e.target.value })) }}
                    placeholder="Email"
                  />
                  {errorEmail && <label
                    className="block uppercase text-red-600 mt-2 text-xs font-bold mb-2"
                    htmlFor="grid-password"
                  >
                    {errorEmail}
                  </label>}
                </div>

                {/* Password */}
                <div className="relative w-full mb-3">
                  <label
                    className="block text-blueGray-600 text-xs font-bold mb-2"
                    htmlFor="grid-password"
                  >
                    Password
                  </label>
                  <input
                    type="password"
                    className="border-0 px-3 py-3 placeholder-blueGray-300 text-blueGray-600 bg-white rounded text-sm shadow focus:outline-none focus:ring w-full ease-linear transition-all duration-150"
                    placeholder="Password"
                    onChange={(e) => {
                      setErrorPass(''); 
                      setUser(prev => ({ ...prev, password: e.target.value }))
                    }}
                  />
                  {errorPass && <label
                    className="block uppercase text-red-600 mt-2 text-xs font-bold mb-2"
                    htmlFor="grid-password"
                  >
                    {errorPass}
                  </label>}
                </div>

                {/* Privacy Policy */}
                <div>
                  <label className="inline-flex items-center cursor-pointer">
                    <input
                      id="customCheckLogin"
                      type="checkbox"
                      className="form-checkbox border-0 rounded text-blueGray-700 ml-1 w-5 h-5 ease-linear transition-all duration-150"
                      onChange={() => {
                        setErrorPolicy('')
                        setPolityCheck( !polityCheck )}} 
                      checked={polityCheck}
                    />
                    <span className="ml-2 text-sm font-semibold text-blueGray-600">
                      {t('I agree with the')}
                      <Link href="/policy"
                         className="text-lightBlue-500 underline-offset-1"
                      >
                        Privacy Policy
                      </Link>
                    </span>
                  </label>
                  {errorPolicy && <label
                    className="block uppercase text-red-600 mt-2 text-xs font-bold mb-2"
                    htmlFor="grid-password"
                  >
                    {errorPolicy}
                  </label>}
                </div>

                <div className="text-center mt-6">
                  <Button onClick={SaveUser} >
                      Create Account
                  </Button>
                </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </LoginBackground>
  )
}
